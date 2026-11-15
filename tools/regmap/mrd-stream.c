// mrd-stream.c (from mrd.c, 2026-11-16): the same READ-ONLY reader, for streaming over ssh to the M3 Max: after each
// "reading" line it waits DELAY_US (default 200000) so the line leaves the machine before the read. A crash then
// leaves the culprit in the M3 Max's copy even when nothing on the M1's disk survives.
// mrd.c: READ-ONLY reads of 32- or 64-bit device words through /dev/mem, one access of exactly that width each.
// usage: mrd <list>      list lines: "<hex address> <4|8>" (anything after the second field is ignored; # starts a comment)
// For every word it first writes "reading <address> <width>" and syncs standard output, then makes the read, then
// writes "<address> <width> <value>". If a read takes the machine down, the last "reading" line names the word.
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

int main(int argc, char **argv)
{
	if (argc != 2) { fprintf(stderr, "usage: mrd <list>\n"); return 2; }
	FILE *f = fopen(argv[1], "r");
	if (!f) { perror(argv[1]); return 2; }
	int fd = open("/dev/mem", O_RDONLY | O_SYNC);
	if (fd < 0) { perror("/dev/mem"); return 2; }
	long pg = sysconf(_SC_PAGESIZE);
	char line[256];
	while (fgets(line, sizeof line, f)) {
		unsigned long long a; int w;
		if (line[0] == '#' || sscanf(line, "%llx %d", &a, &w) != 2) continue;
		if ((w != 4 && w != 8) || (a & (w - 1))) { printf("%#llx %d REFUSED (width or alignment)\n", a, w); continue; }
		printf("reading %#llx %d\n", a, w); fflush(stdout); fsync(1); usleep(getenv("DELAY_US") ? atoi(getenv("DELAY_US")) : 200000);
		void *m = mmap(NULL, pg, PROT_READ, MAP_SHARED, fd, (off_t)(a & ~(unsigned long long)(pg - 1)));
		if (m == MAP_FAILED) { printf("%#llx %d MMAP-FAILED\n", a, w); continue; }
		volatile uint8_t *p = (volatile uint8_t *)m + (a & (pg - 1));
		if (w == 4) printf("%#llx 4 %#010x\n", a, *(volatile uint32_t *)p);
		else printf("%#llx 8 %#018llx\n", a, (unsigned long long)*(volatile uint64_t *)p);
		fflush(stdout); fsync(1);
		munmap(m, pg);
	}
	return 0;
}
