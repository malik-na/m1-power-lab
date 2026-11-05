// SPDX-License-Identifier: GPL-2.0-only
/*
 * m1power: power-research helpers for Apple M1 Macs running Linux.
 *
 * 1. Read-only access to every Apple SMC key. The upstream macsmc-hwmon
 *    driver exposes only the sensors named in the device tree; power
 *    attribution needs the rest (per-rail power, battery power, DC-in energy
 *    accumulators). This module never writes SMC keys and never reads keys
 *    flagged as functions.
 *
 * 2. A wake timer for s2idle. The SMC RTC has no alarm, so rtcwake cannot
 *    end a suspend. The Apple watchdog block has a spare channel whose
 *    interrupt can be enabled without its reset. The timer arms that channel
 *    in chunks (the 32-bit counter at 24 MHz spans ~178 s), re-arms silently
 *    inside s2idle, and raises a hard wakeup event only at the deadline. The
 *    reset-enable bit is never set.
 *
 *   /sys/kernel/debug/m1power/smc_keys     every key: name type size flags hex
 *   /sys/kernel/debug/m1power/smc_watch    write "PSTR PDTR ..." then read values;
 *                                          the key list belongs to that open
 *                                          file (lseek to 0 to read again)
 *   /sys/kernel/debug/m1power/smc_sensors  a fixed set of power keys, for hooks
 *   /sys/kernel/debug/m1power/waketimer    write seconds (0 cancels); read status
 *   /sys/kernel/debug/m1power/wdt_regs     raw watchdog channel registers
 */
#include <linux/debugfs.h>
#include <linux/interrupt.h>
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/ktime.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/of_irq.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
#include <linux/pm_wakeup.h>
#include <linux/seq_file.h>
#include <linux/slab.h>
#include <linux/spinlock.h>
#include <linux/suspend.h>
#include <linux/mfd/macsmc.h>
#include <linux/mfd/syscon.h>
#include <linux/regmap.h>

#define MAX_WATCH 128
#define MAX_VALUE 64

static int wd_channel = 0;
module_param(wd_channel, int, 0444);
MODULE_PARM_DESC(wd_channel, "watchdog channel used for the wake timer; must be 0, the only channel with a BARK interrupt threshold");

static struct dentry *root;

/* ------------------------------------------------------------------ SMC */

static struct platform_device *smc_pdev;
static struct apple_smc *smc;

/* One key list per open smc_watch file, so readers never disturb each other. */
struct watch_list {
	struct mutex lock;
	int count;
	smc_key keys[MAX_WATCH];
};

static const char *const sensor_keys[] = {
	"PSTR", "PDTR", "PPBR", "PHPC", "PMVC", "Pb0f", "Ib0f", "Vb0f",
	"zSPa", "zSPc", "zSPi", "zSLa", "zSLc", "zSEw", "zSEi", "BACC",
};

static smc_key make_key(const char *p)
{
	return ((u32)(u8)p[0] << 24) | ((u32)(u8)p[1] << 16) |
	       ((u32)(u8)p[2] << 8) | (u32)(u8)p[3];
}

static void put_key(struct seq_file *m, smc_key key)
{
	int i;

	for (i = 3; i >= 0; i--) {
		char c = (key >> (i * 8)) & 0xff;

		seq_putc(m, (c >= 0x20 && c < 0x7f) ? c : '?');
	}
}

static void put_value(struct seq_file *m, smc_key key, const struct apple_smc_key_info *info)
{
	u8 buf[MAX_VALUE];
	int ret, i;

	if (!(info->flags & APPLE_SMC_READABLE) || (info->flags & APPLE_SMC_FUNCTION) ||
	    info->size == 0 || info->size > MAX_VALUE) {
		seq_puts(m, "-");
		return;
	}
	ret = apple_smc_read(smc, key, buf, info->size);
	if (ret < 0) {
		seq_printf(m, "E%d", ret);
		return;
	}
	for (i = 0; i < info->size; i++)
		seq_printf(m, "%02x", buf[i]);
}

static void put_line(struct seq_file *m, smc_key key)
{
	struct apple_smc_key_info info;

	put_key(m, key);
	seq_putc(m, ' ');
	if (apple_smc_get_key_info(smc, key, &info) < 0) {
		seq_puts(m, "???? 0 00 -\n");
		return;
	}
	put_key(m, info.type_code);
	seq_printf(m, " %u %02x ", info.size, info.flags);
	put_value(m, key, &info);
	seq_putc(m, '\n');
}

static int smc_keys_show(struct seq_file *m, void *unused)
{
	smc_key key;
	int i;

	for (i = 0; i < smc->key_count; i++) {
		if (apple_smc_get_key_by_index(smc, i, &key) < 0)
			continue;
		put_line(m, key);
		cond_resched();
	}
	return 0;
}
DEFINE_SHOW_ATTRIBUTE(smc_keys);

static int smc_sensors_show(struct seq_file *m, void *unused)
{
	int i;

	seq_printf(m, "BOOT %llu\n", ktime_get_boottime_ns());
	seq_printf(m, "MONO %llu\n", ktime_get_ns());
	for (i = 0; i < ARRAY_SIZE(sensor_keys); i++)
		put_line(m, make_key(sensor_keys[i]));
	return 0;
}
DEFINE_SHOW_ATTRIBUTE(smc_sensors);

static int smc_watch_show(struct seq_file *m, void *unused)
{
	struct watch_list *w = m->private;
	int i;

	mutex_lock(&w->lock);
	seq_printf(m, "BOOT %llu\n", ktime_get_boottime_ns());
	seq_printf(m, "MONO %llu\n", ktime_get_ns());
	for (i = 0; i < w->count; i++)
		put_line(m, w->keys[i]);
	mutex_unlock(&w->lock);
	return 0;
}

static int smc_watch_open(struct inode *inode, struct file *file)
{
	struct watch_list *w;
	int ret;

	w = kzalloc(sizeof(*w), GFP_KERNEL);
	if (!w)
		return -ENOMEM;
	mutex_init(&w->lock);
	ret = single_open(file, smc_watch_show, w);
	if (ret) {
		mutex_destroy(&w->lock);
		kfree(w);
	}
	return ret;
}

static int smc_watch_release(struct inode *inode, struct file *file)
{
	struct seq_file *m = file->private_data;
	struct watch_list *w = m->private;
	int ret;

	ret = single_release(inode, file);
	mutex_destroy(&w->lock);
	kfree(w);
	return ret;
}

static bool is_sep(char c)
{
	return c == ' ' || c == '\n' || c == ',' || c == '\t';
}

static ssize_t smc_watch_write(struct file *file, const char __user *ubuf, size_t len, loff_t *ppos)
{
	struct seq_file *m = file->private_data;
	struct watch_list *w = m->private;
	smc_key keys[MAX_WATCH];
	char *buf, *p;
	int count = 0;

	if (len > MAX_WATCH * 5 + 16)
		return -E2BIG;
	buf = memdup_user_nul(ubuf, len);
	if (IS_ERR(buf))
		return PTR_ERR(buf);

	p = buf;
	while (*p) {
		while (*p && is_sep(*p))
			p++;
		if (!*p)
			break;
		if (strnlen(p, 4) < 4 || count >= MAX_WATCH || (p[4] && !is_sep(p[4]))) {
			kfree(buf);
			return -EINVAL;
		}
		keys[count++] = make_key(p);
		p += 4;
	}
	kfree(buf);

	mutex_lock(&w->lock);
	memcpy(w->keys, keys, count * sizeof(smc_key));
	w->count = count;
	mutex_unlock(&w->lock);
	return len;
}

static const struct file_operations smc_watch_fops = {
	.owner = THIS_MODULE,
	.open = smc_watch_open,
	.read = seq_read,
	.write = smc_watch_write,
	.llseek = seq_lseek,
	.release = smc_watch_release,
};

/* ----------------------------------------------------------- wake timer */

#define WDT_CUR(ch)	((ch) * 0x10 + 0x00)
#define WDT_BITE(ch)	((ch) * 0x10 + 0x04)
#define WDT_BARK(ch)	((ch) * 0x10 + 0x08)	/* interrupt threshold */
#define WDT_CTRL(ch)	((ch) * 0x10 + 0x0c)
#define CTRL_IRQ_EN	BIT(0)
#define CTRL_IRQ_STATUS	BIT(1)
#define CTRL_RESET_EN	BIT(2)
#define WDT_HZ		24000000ULL
#define CHUNK_TICKS	(170ULL * WDT_HZ)
#define STORM_LIMIT	64
#define GRACE_TICKS	(3ULL * WDT_HZ)	/* re-wake chunk for a deadline lost to suspend entry */

/* ------------------------------------------------------------------ pmgr */

/*
 * Hardware state of every PMGR power-state register in the device tree, read
 * through the PMGR's own syscon regmap (the same, non-posted, accessor the
 * pmgr-pwrstate driver uses); read-only. genpd reports what Linux asked for;
 * these registers say what the hardware is doing, including domains that
 * auto-PM gates on its own while genpd calls them "on".
 *
 *   pmgr_ps      one read now: target, actual, min, auto, flags per domain
 *   pmgr_duty    100 reads 50 ms apart: share of reads gated (actual < 0xf)
 *   pmgr_s2idle  the same snapshot, taken by the wake-timer interrupt while
 *                the system was in s2idle (devices suspended)
 */
#define PMGR_MAX 160
#define PMGR_DUTY_SAMPLES 100
struct pmgr_dom {
	struct regmap *map;
	u32 offset;
	const char *label;
};
static struct pmgr_dom pmgr_doms[PMGR_MAX];
static int pmgr_count;
static u32 pmgr_sleep_regs[PMGR_MAX];
static u64 pmgr_sleep_at_ns, pmgr_sleep_snaps;
static DEFINE_SPINLOCK(pmgr_lock);

static void pmgr_init(void)
{
	struct device_node *np;

	for_each_compatible_node(np, NULL, "apple,pmgr-pwrstate") {
		struct device_node *parent;
		struct regmap *map;
		u32 offset;

		if (pmgr_count >= PMGR_MAX)
			break;
		if (!of_device_is_available(np) || of_property_read_u32(np, "reg", &offset))
			continue;
		parent = of_get_parent(np);
		map = parent ? syscon_node_to_regmap(parent) : ERR_PTR(-ENODEV);
		of_node_put(parent);
		if (IS_ERR(map))
			continue;
		pmgr_doms[pmgr_count].map = map;
		pmgr_doms[pmgr_count].offset = offset;
		if (of_property_read_string(np, "label", &pmgr_doms[pmgr_count].label))
			pmgr_doms[pmgr_count].label = np->name;
		pmgr_count++;
	}
}

static u32 pmgr_read(int i)
{
	u32 v = 0;

	if (regmap_read(pmgr_doms[i].map, pmgr_doms[i].offset, &v))
		return U32_MAX;
	return v;
}

static void pmgr_put(struct seq_file *m, int i, u32 v)
{
	if (v == U32_MAX) {
		seq_printf(m, "%-16s read-error\n", pmgr_doms[i].label);
		return;
	}
	seq_printf(m, "%-16s raw=%08x target=%x actual=%x min=%x auto=%d busy=%d was_clkgated=%d was_pwrgated=%d\n",
		   pmgr_doms[i].label, v, v & 0xf, (v >> 4) & 0xf, (v >> 16) & 0xf,
		   !!(v & BIT(28)), !!(v & BIT(11)), !!(v & BIT(9)), !!(v & BIT(8)));
}

static int pmgr_ps_show(struct seq_file *m, void *unused)
{
	int i;

	for (i = 0; i < pmgr_count; i++)
		pmgr_put(m, i, pmgr_read(i));
	return 0;
}
DEFINE_SHOW_ATTRIBUTE(pmgr_ps);

static int pmgr_duty_show(struct seq_file *m, void *unused)
{
	u16 *gated, *pwrgated;
	int i, n;

	gated = kcalloc(pmgr_count, sizeof(*gated), GFP_KERNEL);
	pwrgated = kcalloc(pmgr_count, sizeof(*pwrgated), GFP_KERNEL);
	if (!gated || !pwrgated) {
		kfree(gated);
		kfree(pwrgated);
		return -ENOMEM;
	}
	for (n = 0; n < PMGR_DUTY_SAMPLES; n++) {
		for (i = 0; i < pmgr_count; i++) {
			u32 v = pmgr_read(i), actual = (v >> 4) & 0xf;

			if (v == U32_MAX)
				continue;
			if (actual < 0xf)
				gated[i]++;
			if (actual == 0)
				pwrgated[i]++;
		}
		if (msleep_interruptible(50))
			break;
	}
	seq_printf(m, "# %d reads 50 ms apart; share of reads with actual < f (gated) and actual = 0 (power-gated)\n", n);
	for (i = 0; i < pmgr_count; i++)
		seq_printf(m, "%-16s gated=%3d%% pwrgated=%3d%%\n", pmgr_doms[i].label,
			   n ? 100 * gated[i] / n : 0, n ? 100 * pwrgated[i] / n : 0);
	kfree(gated);
	kfree(pwrgated);
	return 0;
}
DEFINE_SHOW_ATTRIBUTE(pmgr_duty);

/*
 * pmgr_set: write "label state" (state 0, 4 or f) to drive one PMGR
 * power-state register directly, for measuring what a domain costs. Only
 * domains whose label starts with an allowed prefix can be written: gating
 * a block that a running driver touches raises an SError. Like the
 * pmgr-pwrstate driver, the write clears auto-PM and the sticky flags, then
 * waits up to 100 ms for the actual state to follow.
 */
static const char *const pmgr_set_allowed[] = { "atc", "dispext" };

static ssize_t pmgr_set_write(struct file *file, const char __user *ubuf, size_t len, loff_t *ppos)
{
	char buf[48], label[32];
	unsigned int state;
	int i, j, ret = -ENOENT;
	u32 v = 0;

	if (len >= sizeof(buf))
		return -EINVAL;
	if (copy_from_user(buf, ubuf, len))
		return -EFAULT;
	buf[len] = '\0';
	if (sscanf(buf, "%31s %x", label, &state) != 2 || (state != 0 && state != 4 && state != 0xf))
		return -EINVAL;
	for (j = 0; j < ARRAY_SIZE(pmgr_set_allowed); j++)
		if (!strncmp(label, pmgr_set_allowed[j], strlen(pmgr_set_allowed[j])))
			break;
	if (j == ARRAY_SIZE(pmgr_set_allowed))
		return -EPERM;
	for (i = 0; i < pmgr_count; i++) {
		if (strcmp(pmgr_doms[i].label, label))
			continue;
		ret = regmap_update_bits(pmgr_doms[i].map, pmgr_doms[i].offset,
					 BIT(28) | BIT(9) | BIT(8) | 0xf, state);
		if (ret)
			break;
		ret = regmap_read_poll_timeout(pmgr_doms[i].map, pmgr_doms[i].offset, v,
					       ((v >> 4) & 0xf) == state, 100, 100000);
		pr_info("m1power: pmgr %s -> %x: actual %x (%d)\n", label, state, (v >> 4) & 0xf, ret);
		break;
	}
	return ret ? ret : len;
}

static const struct file_operations pmgr_set_fops = {
	.owner = THIS_MODULE,
	.write = pmgr_set_write,
	.llseek = noop_llseek,
};

/* Called from the wake-timer interrupt while suspending (devices suspended
 * when it fires inside s2idle). syscon regmaps use a spinlock, so this is
 * safe in hard-IRQ context. */
static void pmgr_snapshot_sleep(void)
{
	unsigned long flags;
	int i;

	spin_lock_irqsave(&pmgr_lock, flags);
	for (i = 0; i < pmgr_count; i++)
		pmgr_sleep_regs[i] = pmgr_read(i);
	pmgr_sleep_at_ns = ktime_get_boottime_ns();
	pmgr_sleep_snaps++;
	spin_unlock_irqrestore(&pmgr_lock, flags);
}

static int pmgr_s2idle_show(struct seq_file *m, void *unused)
{
	unsigned long flags;
	u32 *regs;
	u64 at, snaps;
	int i;

	regs = kmalloc_array(PMGR_MAX, sizeof(*regs), GFP_KERNEL);
	if (!regs)
		return -ENOMEM;
	spin_lock_irqsave(&pmgr_lock, flags);
	memcpy(regs, pmgr_sleep_regs, sizeof(pmgr_sleep_regs));
	at = pmgr_sleep_at_ns;
	snaps = pmgr_sleep_snaps;
	spin_unlock_irqrestore(&pmgr_lock, flags);
	seq_printf(m, "# snapshots %llu, last at boottime %llu ns (now %llu)\n", snaps, at,
		   ktime_get_boottime_ns());
	if (snaps)
		for (i = 0; i < pmgr_count; i++)
			pmgr_put(m, i, regs[i]);
	kfree(regs);
	return 0;
}
DEFINE_SHOW_ATTRIBUTE(pmgr_s2idle);

/* ------------------------------------------------------------ wake timer */

static void __iomem *wdt_base;
static int wdt_irq = -1;
static bool wdt_irq_wake;
static DEFINE_SPINLOCK(timer_lock);
static struct wakeup_source *wake_ws;
static u64 remaining_ticks;	/* ticks still to wait after the current chunk */
static u32 chunk_ticks;		/* ticks in the current chunk */
static bool armed;
static u64 armed_at_boot_ns, deadline_boot_ns;
static u64 fired_chunks, fired_total, last_fire_boot_ns, spurious_fires;
static unsigned int consecutive_spurious;	/* per arm; reset by every write */
static bool storm_disabled;
static char last_error[64];
/*
 * The deadline fired but no resume has consumed it yet. A hard wakeup raised
 * before freeze_processes() is discarded by pm_wakeup_clear(0), so a deadline
 * that passes while the system is still awake or entering suspend would
 * otherwise leave it in s2idle with no timer armed.
 */
static bool pending_wake;
static u64 pending_at_ns;	/* boottime when the deadline fired */
#define PENDING_MAX_AGE_NS (60ULL * NSEC_PER_SEC)
static bool suspending;		/* between PM_SUSPEND_PREPARE and PM_POST_SUSPEND */
static bool pm_nb_registered;

static void wdt_stop_locked(void)
{
	writel_relaxed(CTRL_IRQ_STATUS, wdt_base + WDT_CTRL(wd_channel));
	writel_relaxed(0, wdt_base + WDT_CTRL(wd_channel));
	writel_relaxed(0, wdt_base + WDT_CUR(wd_channel));
}

static void wdt_start_chunk_locked(void)
{
	u64 ticks = min_t(u64, remaining_ticks, CHUNK_TICKS);

	if (ticks < WDT_HZ / 100)
		ticks = WDT_HZ / 100;
	chunk_ticks = ticks;
	remaining_ticks -= min(remaining_ticks, ticks);
	writel_relaxed(0, wdt_base + WDT_CTRL(wd_channel));
	/* BARK raises the interrupt; BITE only matters with RESET_EN, which is
	 * never set, but keep it beyond BARK anyway. */
	writel_relaxed(U32_MAX, wdt_base + WDT_BITE(wd_channel));
	writel_relaxed(chunk_ticks, wdt_base + WDT_BARK(wd_channel));
	writel(0, wdt_base + WDT_CUR(wd_channel));
	/* Clear any stale status (write-one-clears), then enable only the
	 * interrupt. CTRL_RESET_EN is never set. */
	writel_relaxed(CTRL_IRQ_STATUS, wdt_base + WDT_CTRL(wd_channel));
	writel(CTRL_IRQ_EN, wdt_base + WDT_CTRL(wd_channel));
}

static irqreturn_t wdt_irq_handler(int irq, void *data)
{
	unsigned long flags;
	u32 cur;
	bool wake = false, snap;

	spin_lock_irqsave(&timer_lock, flags);
	snap = suspending;
	cur = readl_relaxed(wdt_base + WDT_CUR(wd_channel));
	fired_total++;
	last_fire_boot_ns = ktime_get_boottime_ns();

	if (!armed) {
		wdt_stop_locked();
		goto out;
	}

	/*
	 * The status can be latched from before the channel was armed and the
	 * line asserts as soon as the interrupt is enabled. Time is frozen in
	 * s2idle, so judge the fire by the hardware counter itself: anything
	 * well short of the programmed chunk is stale; clear it and keep going.
	 */
	if ((u64)cur + WDT_HZ / 2 < chunk_ticks) {
		spurious_fires++;
		if (++consecutive_spurious > STORM_LIMIT) {
			/* Not a deadline: report it in the status file and leave
			 * waking to the real wake sources. */
			wdt_stop_locked();
			armed = false;
			pending_wake = false;
			storm_disabled = true;
			strscpy(last_error, "interrupt storm: timer disabled", sizeof(last_error));
			disable_irq_nosync(irq);
			goto out;
		}
		writel_relaxed(CTRL_IRQ_STATUS, wdt_base + WDT_CTRL(wd_channel));
		writel(CTRL_IRQ_EN, wdt_base + WDT_CTRL(wd_channel));
		goto out;
	}

	consecutive_spurious = 0;
	fired_chunks++;
	if (remaining_ticks) {
		wdt_start_chunk_locked();
	} else {
		pending_wake = true;
		pending_at_ns = ktime_get_boottime_ns();
		if (suspending) {
			/* This wake may land before freeze_processes(), which
			 * discards it. Keep a short chunk running so the system
			 * is woken again from s2idle; PM_POST_SUSPEND stops it. */
			remaining_ticks = GRACE_TICKS;
			wdt_start_chunk_locked();
		} else {
			wdt_stop_locked();
			armed = false;
		}
		wake = true;
	}
out:
	spin_unlock_irqrestore(&timer_lock, flags);
	if (snap)
		pmgr_snapshot_sleep();
	if (wake)
		pm_wakeup_ws_event(wake_ws, 2000, true);
	return IRQ_HANDLED;
}

static int waketimer_show(struct seq_file *m, void *unused)
{
	unsigned long flags;
	u64 now = ktime_get_boottime_ns();

	spin_lock_irqsave(&timer_lock, flags);
	seq_printf(m, "channel %d\nirq %d\nirq_wake %d\narmed %d\n", wd_channel, wdt_irq,
		   wdt_irq_wake, armed);
	if (armed)
		seq_printf(m, "remaining_s %lld\n",
			   (long long)(deadline_boot_ns > now ? (deadline_boot_ns - now) / NSEC_PER_SEC : 0));
	seq_printf(m, "armed_at_boot_ns %llu\ndeadline_boot_ns %llu\n", armed_at_boot_ns, deadline_boot_ns);
	seq_printf(m, "fired_chunks %llu\nfired_total %llu\nspurious_fires %llu\nlast_fire_boot_ns %llu\n",
		   fired_chunks, fired_total, spurious_fires, last_fire_boot_ns);
	seq_printf(m, "consecutive_spurious %u\npending_wake %d\nsuspending %d\npm_notifier %d\n",
		   consecutive_spurious, pending_wake, suspending, pm_nb_registered);
	seq_printf(m, "storm_disabled %d\nlast_error %s\n", storm_disabled, last_error[0] ? last_error : "-");
	spin_unlock_irqrestore(&timer_lock, flags);
	return 0;
}

static int waketimer_open(struct inode *inode, struct file *file)
{
	return single_open(file, waketimer_show, NULL);
}

static ssize_t waketimer_write(struct file *file, const char __user *ubuf, size_t len, loff_t *ppos)
{
	unsigned long flags;
	unsigned int seconds;
	int ret;

	ret = kstrtouint_from_user(ubuf, len, 10, &seconds);
	if (ret)
		return ret;
	if (seconds > 7 * 24 * 3600)
		return -ERANGE;

	spin_lock_irqsave(&timer_lock, flags);
	/* Cancelling always works; arming after a storm does not. */
	if (seconds && storm_disabled) {
		spin_unlock_irqrestore(&timer_lock, flags);
		return -EIO;
	}
	wdt_stop_locked();
	armed = false;
	pending_wake = false;
	consecutive_spurious = 0;
	if (seconds) {
		armed_at_boot_ns = ktime_get_boottime_ns();
		deadline_boot_ns = armed_at_boot_ns + (u64)seconds * NSEC_PER_SEC;
		remaining_ticks = (u64)seconds * WDT_HZ;
		fired_chunks = 0;
		armed = true;
		wdt_start_chunk_locked();
	}
	spin_unlock_irqrestore(&timer_lock, flags);
	return len;
}

static const struct file_operations waketimer_fops = {
	.owner = THIS_MODULE,
	.open = waketimer_open,
	.read = seq_read,
	.write = waketimer_write,
	.llseek = seq_lseek,
	.release = single_release,
};

static int wdt_regs_show(struct seq_file *m, void *unused)
{
	int ch;

	for (ch = 0; ch < 3; ch++)
		seq_printf(m, "wd%d cur=%08x bite=%08x bark=%08x ctrl=%08x\n", ch,
			   readl(wdt_base + WDT_CUR(ch)), readl(wdt_base + WDT_BITE(ch)),
			   readl(wdt_base + WDT_BARK(ch)), readl(wdt_base + WDT_CTRL(ch)));
	return 0;
}
DEFINE_SHOW_ATTRIBUTE(wdt_regs);

static int wdt_pm_notify(struct notifier_block *nb, unsigned long action, void *data)
{
	unsigned long flags;

	spin_lock_irqsave(&timer_lock, flags);
	switch (action) {
	case PM_SUSPEND_PREPARE:
		suspending = true;
		/* The deadline expired before this suspend started: wake shortly
		 * after entering s2idle instead of sleeping until a key press. */
		/*
		 * Only a suspend that follows the deadline closely (a sleep test
		 * or guard that armed it, delayed by inhibitors) is re-woken; a
		 * deadline that went stale while the user worked is dropped so it
		 * cannot cut a later, unrelated suspend short.
		 */
		if (pending_wake && ktime_get_boottime_ns() - pending_at_ns > PENDING_MAX_AGE_NS)
			pending_wake = false;
		if (pending_wake && !armed && !storm_disabled) {
			remaining_ticks = GRACE_TICKS;
			armed = true;
			wdt_start_chunk_locked();
		}
		break;
	case PM_POST_SUSPEND:
		suspending = false;
		/* Resumed: the deadline is consumed. Only a grace chunk can be
		 * armed while pending_wake is set (every write clears it). */
		if (pending_wake) {
			pending_wake = false;
			wdt_stop_locked();
			armed = false;
		}
		break;
	}
	spin_unlock_irqrestore(&timer_lock, flags);
	return NOTIFY_DONE;
}

static struct notifier_block wdt_pm_nb = {
	.notifier_call = wdt_pm_notify,
};

static int waketimer_init(void)
{
	struct device_node *np;
	u32 ctrl;
	int ret;

	np = of_find_compatible_node(NULL, NULL, "apple,wdt");
	if (!np)
		return -ENODEV;
	wdt_base = of_iomap(np, 0);
	wdt_irq = irq_of_parse_and_map(np, 0);
	of_node_put(np);
	if (!wdt_base || wdt_irq <= 0) {
		pr_warn("m1power: watchdog registers or interrupt unavailable\n");
		return -ENODEV;
	}

	ctrl = readl(wdt_base + WDT_CTRL(wd_channel));
	if (ctrl & (CTRL_RESET_EN | CTRL_IRQ_EN)) {
		pr_warn("m1power: watchdog channel %d is in use (ctrl=%08x); wake timer disabled\n",
			wd_channel, ctrl);
		return -EBUSY;
	}
	writel(CTRL_IRQ_STATUS, wdt_base + WDT_CTRL(wd_channel));
	writel(0, wdt_base + WDT_CTRL(wd_channel));

	wake_ws = wakeup_source_register(NULL, "m1power_waketimer");
	if (!wake_ws)
		return -ENOMEM;
	ret = request_irq(wdt_irq, wdt_irq_handler, IRQF_NO_SUSPEND | IRQF_SHARED, "m1power-waketimer",
			  &wdt_base);
	if (ret) {
		wakeup_source_unregister(wake_ws);
		wake_ws = NULL;
		return ret;
	}
	wdt_irq_wake = !enable_irq_wake(wdt_irq);
	ret = register_pm_notifier(&wdt_pm_nb);
	if (ret) {
		pr_warn("m1power: cannot register PM notifier (%d)\n", ret);
		if (wdt_irq_wake)
			disable_irq_wake(wdt_irq);
		wdt_irq_wake = false;
		free_irq(wdt_irq, &wdt_base);
		wakeup_source_unregister(wake_ws);
		wake_ws = NULL;
		return ret;
	}
	pm_nb_registered = true;
	return 0;
}

static void waketimer_exit(void)
{
	unsigned long flags;

	if (!wake_ws)
		return;
	if (pm_nb_registered)
		unregister_pm_notifier(&wdt_pm_nb);
	pm_nb_registered = false;
	spin_lock_irqsave(&timer_lock, flags);
	armed = false;
	pending_wake = false;
	wdt_stop_locked();
	spin_unlock_irqrestore(&timer_lock, flags);
	if (wdt_irq_wake)
		disable_irq_wake(wdt_irq);
	free_irq(wdt_irq, &wdt_base);
	wakeup_source_unregister(wake_ws);
	wake_ws = NULL;
}

/* ---------------------------------------------------------------- module */

static int __init m1power_init(void)
{
	struct device_node *np;
	int ret;

	if (wd_channel != 0) {
		pr_warn("m1power: wd_channel=%d rejected: only watchdog channel 0 has a BARK interrupt threshold\n",
			wd_channel);
		return -EINVAL;
	}
	np = of_find_compatible_node(NULL, NULL, "apple,smc");
	if (!np)
		return -ENODEV;
	smc_pdev = of_find_device_by_node(np);
	of_node_put(np);
	if (!smc_pdev)
		return -ENODEV;
	smc = platform_get_drvdata(smc_pdev);
	if (!smc || !smc->key_count) {
		put_device(&smc_pdev->dev);
		return -EPROBE_DEFER;
	}

	pmgr_init();
	root = debugfs_create_dir("m1power", NULL);
	debugfs_create_file("smc_keys", 0400, root, NULL, &smc_keys_fops);
	debugfs_create_file("smc_watch", 0600, root, NULL, &smc_watch_fops);
	debugfs_create_file("smc_sensors", 0400, root, NULL, &smc_sensors_fops);

	ret = waketimer_init();
	if (ret) {
		pr_warn("m1power: wake timer unavailable (%d)\n", ret);
	} else {
		debugfs_create_file("waketimer", 0600, root, NULL, &waketimer_fops);
	}
	if (wdt_base)
		debugfs_create_file("wdt_regs", 0400, root, NULL, &wdt_regs_fops);
	if (pmgr_count) {
		debugfs_create_file("pmgr_ps", 0400, root, NULL, &pmgr_ps_fops);
		debugfs_create_file("pmgr_duty", 0400, root, NULL, &pmgr_duty_fops);
		debugfs_create_file("pmgr_s2idle", 0400, root, NULL, &pmgr_s2idle_fops);
		debugfs_create_file("pmgr_set", 0200, root, NULL, &pmgr_set_fops);
	}

	pr_info("m1power: %u SMC keys (read-only), %d PMGR domains, wake timer %s\n",
		smc->key_count, pmgr_count, wake_ws ? "ready" : "off");
	return 0;
}

static void __exit m1power_exit(void)
{
	/* debugfs first, then notifier, timer and IRQ (waketimer_exit), then
	 * the register mapping they all use. */
	debugfs_remove_recursive(root);
	waketimer_exit();
	if (wdt_base)
		iounmap(wdt_base);
	put_device(&smc_pdev->dev);
}

module_init(m1power_init);
module_exit(m1power_exit);
MODULE_DESCRIPTION("Apple M1 power research: SMC key access and an s2idle wake timer");
MODULE_LICENSE("GPL");
MODULE_SOFTDEP("pre: macsmc");
