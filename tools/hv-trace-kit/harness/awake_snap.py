# hv script: awake_snap(list_path, tag): one touch-map snapshot of another word list, taken in
# the hypervisor shell (guest paused), then the touch map's own list is put back. For words that
# should have a value with the guest awake without growing the touch map's list (its power-manager
# and always-on part becomes detach()'s wake-snapshot list, which is limited to 320 words).
# Use before detach(), e.g. PRE='hv.run_script(".../awake_snap.py")\nawake_snap("<list>", "awake-extra")\n'
# with harness/detach135.sh.
import json


def awake_snap(list_path, tag="awake-extra"):
    tm = globals().get("touch_map")
    if tm is None:
        print("[awake-snap] no touch_map in this shell: nothing read")
        return
    orig = tm.snap_list
    try:
        tm.snap_list = [(int(a), n) for a, n in json.load(open(list_path))]
        tm.snapshot(tag)
        print("[awake-snap] snapshot %r: %d entries from %s" % (tag, len(tm.snap_list), list_path))
    finally:
        tm.snap_list = orig


print("[awake-snap] awake_snap() defined")
