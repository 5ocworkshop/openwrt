// <FILE>target/linux/bcm4908/base-files/usr/share/ac86u/orc_wan_led_monitor.uc</FILE> - <DESC>Run the AC86U WAN reconciler once or from kernel link and route events.</DESC>
// <VERS>VERSION: 0.1.2</VERS>
// <WCTX>Keep one event-driven WAN policy synchronized across startup and boot release.</WCTX>
// <CLOG>Use event-loop signals, retain the VM-owned listener and protect lock/status writes with private canonical RAM paths.</CLOG>

import * as fs from "fs";
import * as r from "rtnl";
import * as uci from "uci";
import * as loop from "uloop";
import { reconcile_wan_led } from "fnc_reconcile_wan_led";
import { wan_led_runtime_path } from "fnc_wan_led_runtime_path";

let mode = getenv("AC86U_WAN_LED_MODE") || "once";
let sysfs = getenv("AC86U_WAN_LED_SYSFS") || "/sys/class/leds";
let paths = {
    sysfs,
    board: getenv("AC86U_WAN_LED_BOARD_FILE") || "/tmp/sysinfo/board_name",
    boot: getenv("AC86U_WAN_LED_BOOT_STATUS") || sysfs + "/wan/device/boot_waypoint",
    lock: getenv("AC86U_WAN_LED_LOCK") || "/tmp/ac86u-wan-led/lock",
    status: getenv("AC86U_WAN_LED_STATUS") || "/tmp/ac86u-wan-led/status.json",
    config: getenv("AC86U_WAN_LED_CONFIG_DIR") || "/etc/config"
};
let ctx = { fs, r, cursor: uci.cursor(paths.config), paths };
let watcher = null, heartbeat = null, watch_lock = null;
let signals = [], status_sequence = 0;
let watch_owned = false;
let failure = null, stopping = false, event_count = 0, last_result = null;
let pid = int(split(fs.readfile("/proc/self/stat") || "", " ")[0]);

function record_status(stage) {
    let record = { pid, updated_utc: time(), stage, event_count, last_result };
    if (failure != null) record.error = "" + failure;
    wan_led_runtime_path(fs, paths.status, false);
    let text = sprintf("%J\n", record);
    let temporary = paths.status + ".tmp." + pid + "." + time() + "." + status_sequence++;
    wan_led_runtime_path(fs, temporary, false);
    if (fs.writefile(temporary, text) != length(text) || fs.rename(temporary, paths.status) != true)
        die("Cannot atomically publish WAN policy status: " + paths.status);
}

function network_event() {
    event_count++;
    try {
        last_result = reconcile_wan_led(ctx, false);
        record_status("running");
        if (last_result.changed)
            warn("ac86u-wan-led: state=" + last_result.state + " changed=" + last_result.changed + "\n");
    } catch (error) {
        failure = error;
        loop.end();
    }
}

function heartbeat_tick() {
    try {
        record_status("running");
        warn("ac86u-wan-led: heartbeat events=" + event_count + " state=" + last_result.state + "\n");
        heartbeat.set(60000);
    } catch (error) {
        failure = error;
        loop.end();
    }
}

function stop_monitor() {
    stopping = true;
    loop.end();
}

try {
    if (mode != "once" && mode != "watch" && mode != "dry-run")
        die("Unknown WAN LED mode");
    let names = keys(paths);
    for (let i = 0; i < length(names); i++) {
        let path = paths[names[i]];
        if (substr(path, 0, 1) != "/" || index(path, "/../") >= 0 || match(path, /[\r\n]/))
            die("Invalid WAN policy path: " + names[i]);
    }
    if (index(paths.lock, "/tmp/") != 0 || index(paths.status, "/tmp/") != 0)
        die("WAN policy lock/status must be RAM paths under /tmp");
    if (mode != "watch") {
        printf("%J\n", reconcile_wan_led(ctx, mode == "dry-run"));
    }
    else if (trim(fs.readfile(paths.board) || "") != "asus,rt-ac86u") {
        printf("%J\n", { state: "not_applicable", changed: 0 });
    }
    else {
        if (!pid) die("Cannot establish WAN monitor PID");
        wan_led_runtime_path(fs, paths.status, false);
        wan_led_runtime_path(fs, paths.status + ".watch.lock", false);
        watch_lock = fs.open(paths.status + ".watch.lock", "a");
        if (!watch_lock || watch_lock.lock("xn") != true)
            die("A WAN monitor already owns this status path");
        watch_owned = true;
        loop.init();
        let names = ["INT", "TERM", "HUP"];
        for (let i = 0; i < length(names); i++) {
            let handler = loop.signal(names[i], stop_monitor);
            if (!handler) die("Cannot register WAN signal watcher: " + names[i]);
            push(signals, handler);
        }
        watcher = r.listener(network_event, [
            r.const.RTM_NEWLINK, r.const.RTM_DELLINK, r.const.RTM_NEWROUTE, r.const.RTM_DELROUTE
        ], [r.const.RTNLGRP_LINK, r.const.RTNLGRP_IPV4_ROUTE, r.const.RTNLGRP_IPV6_ROUTE]);
        if (!watcher) die("Cannot subscribe to WAN link/route events: " + r.error());
        last_result = reconcile_wan_led(ctx, false);
        record_status("running");
        warn("ac86u-wan-led: started state=" + last_result.state + "\n");
        heartbeat = loop.timer(60000, heartbeat_tick);
        if (!heartbeat) die("Cannot create WAN monitor heartbeat: " + loop.error());
        loop.run();
        if (failure == null && !stopping) failure = "WAN event loop ended unexpectedly";
    }
} catch (error) { failure = error; }

if (heartbeat) heartbeat.cancel();
// Retain watcher for its VM finalizer. Explicit rtnl.close() is re-finalized by
// this runtime and crashes at VM shutdown; native process tests cover ownership.
for (let i = 0; i < length(signals); i++) signals[i].delete();
if (watch_owned) {
    try { record_status(failure == null ? "complete" : "failed"); }
    catch (error) { if (failure == null) failure = error; }
    if (watch_lock.lock("u") != true && failure == null) failure = "Cannot unlock WAN monitor ownership";
    if (watch_lock.close() != true && failure == null) failure = "Cannot close WAN monitor ownership";
    loop.done();
}
else if (watch_lock) watch_lock.close();
if (failure != null) {
    warn("ac86u-wan-led: FAILED: " + failure + "\n");
    exit(1);
}

// <FILE>target/linux/bcm4908/base-files/usr/share/ac86u/orc_wan_led_monitor.uc</FILE> - <DESC>Run the AC86U WAN reconciler once or from kernel link and route events.</DESC>
// <VERS>END OF VERSION: 0.1.2</VERS>
