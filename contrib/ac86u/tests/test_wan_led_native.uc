// <FILE>contrib/ac86u/tests/test_wan_led_native.uc</FILE> - <DESC>Exercise WAN reconciliation in native ucode with isolated real filesystem controls.</DESC>
// <VERS>VERSION: 0.1.4</VERS>
// <WCTX>Verify native VM, filesystem locking and GPIO-file operations without touching LEDs or routes.</WCTX>
// <CLOG>Port the focused hardware regression to native OpenWrt source paths.</CLOG>

import * as fs from "fs";
import * as native_rtnl from "rtnl";
import { reconcile_wan_led } from "fnc_reconcile_wan_led";
import { wan_led_snapshot } from "col_wan_led_policy";

let active, rtnl_constants = native_rtnl.const;
function check(ok, message) { if (!ok) die(message); }
function save(path, data) {
    check(fs.writefile(path, data) == length(data), "Fixture write failed: " + path);
}
function read_control(path) {
    let data = fs.readfile(path);
    // Adapt active-trigger readback; write_control also models brightness clearing on detach.
    return type(data) == "string" && match(path, /\/trigger$/) &&
        match(trim(data), /^(none|netdev|default-on)$/) ? "[" + trim(data) + "]\n" : data;
}
function write_control(path, data) {
    check(index(path, active.leds + "/") == 0, "Production write escaped fixture LEDs");
    let detach = match(path, /\/trigger$/) && trim(read_control(path)) != "[none]" &&
        trim(read_control(path)) != "[" + trim(data) + "]";
    active.writes++;
    let written = fs.writefile(path, data);
    if (written == length(data) && detach)
        save(substr(path, 0, length(path) - length("trigger")) + "brightness", "0\n");
    return written;
}
function request_snapshot(command, flags, data) {
    check(type(command) == "int" && type(flags) == "int" && type(data) == "object", "Invalid rtnetlink request DTO");
    check(flags == rtnl_constants.NLM_F_DUMP, "Unexpected rtnetlink request flags");
    if (command == rtnl_constants.RTM_GETLINK) return active.input.links == null ?
        [{ ifname: "wan", carrier: true, flags: 1 }] : active.input.links;
    check(command == rtnl_constants.RTM_GETROUTE && type(data.family) == "int" &&
        (data.family == rtnl_constants.AF_INET || data.family == rtnl_constants.AF_INET6), "Unexpected snapshot request");
    active.routes++;
    if (active.input.route_error) return false;
    let routes = data.family == rtnl_constants.AF_INET ? active.input.v4 : active.input.v6;
    return routes == null ? [] : routes;
}
function lock_released(path) {
    if (!fs.stat(path)) return;
    let file = fs.open(path, "a");
    check(file != null, "Cannot inspect fixture lock");
    let acquired = file.lock("xn");
    if (acquired == true) file.lock("u");
    check(file.close() == true && acquired == true, "Reconciliation retained its lock");
}
function run_case(input, root, number) {
    let base = root + "/case-" + number;
    check(fs.mkdir(base, 448), "Cannot create fresh fixture case");
    active = { input, leds: base + "/leds", writes: 0, routes: 0 };
    check(fs.mkdir(active.leds, 448), "Cannot create fixture LED directory");
    let names = ["wan", "wan-error"];
    for (let i = 0; i < length(names); i++) {
        let led = active.leds + "/" + names[i];
        check(fs.mkdir(led, 448), "Cannot create fixture LED controls");
        save(led + "/trigger", names[i] == "wan-error" && input.red_trigger ? input.red_trigger + "\n" : "none\n");
        save(led + "/brightness", input.lit || (names[i] == "wan-error" && input.red_lit) ? "9\n" : "0\n");
        save(led + "/max_brightness", "9\n");
    }
    for (let i = 0; i < 4; i++)
        save(active.leds + "/wan/" + ["device_name", "link", "rx", "tx"][i], "0\n");
    save(base + "/board", (input.other_board ? "other,board" : "asus,rt-ac86u") + "\n");
    save(base + "/boot", input.boot || "completed=f zone=4 step=4 failed=0 panic=0 released=1 finishing=0\n");
    let lock_path = base + "/lock", guarded_parent = null, original_mode = null;
    if (input.unsafe) {
        save(base + "/untouched", "preserve\n");
        if (input.unsafe == "leaf") check(fs.symlink(base + "/untouched", lock_path), "Cannot create fixture leaf symlink");
        if (input.unsafe == "ancestor") {
            check(fs.symlink(base, base + "/alias"), "Cannot create fixture ancestor symlink");
            lock_path = base + "/alias/lock";
        }
        if (input.unsafe == "parent") {
            guarded_parent = base + "/public";
            check(fs.mkdir(guarded_parent, 493), "Cannot create nonprivate fixture parent");
            original_mode = fs.lstat(guarded_parent).mode;
            lock_path = guarded_parent + "/lock";
        }
    }
    let system = { system: { ".type": "system", leds_off: input.alloff ? "1" : "0" },
        wan: { ".type": "led", sysfs: "wan", trigger: "netdev", dev: "wan", mode: "link rx tx" } };
    if (input.custom) system.wan[input.custom[0]] = input.custom[1];
    if (input.custom_red) system.red = { ".type": "led", sysfs: "wan-error" };
    let ctx = {
        fs: { readfile: read_control, writefile: write_control, open: fs.open, stat: fs.stat,
            lstat: fs.lstat, realpath: fs.realpath, dirname: fs.dirname, mkdir: fs.mkdir },
        r: { request: request_snapshot, error: () => "injected snapshot error",
            const: rtnl_constants },
        cursor: { unload: () => true, load: () => true, get_all: () => system },
        paths: { board: base + "/board", boot: base + "/boot", sysfs: active.leds, lock: lock_path }
    };
    let result = null, failure = null;
    try { result = reconcile_wan_led(ctx, input.dryrun == true); } catch (error) { failure = error; }
    if (!input.unsafe) lock_released(ctx.paths.lock);
    else {
        check(fs.readfile(base + "/untouched") == "preserve\n", "Rejected path changed its target");
        if (guarded_parent) check(fs.lstat(guarded_parent).mode == original_mode, "Rejected parent permissions changed");
    }
    if (input.error) check(failure != null && active.writes == 0, "Expected failure before LED writes");
    else {
        if (failure != null) die(failure);
        check(result.state == input.state, "Unexpected state: " + result.state);
        if (input.no_write || input.dryrun) check(active.writes == 0, "Unexpected LED write");
        if (input.no_routes) check(active.routes == 0, "Carrier/ownership gate queried routes");
        if (input.state == "off" || input.state == "user_off")
            for (let i = 0; i < length(names); i++)
                check(trim(fs.readfile(active.leds + "/" + names[i] + "/brightness")) == "0", "Off state left an LED on");
        if (!input.dryrun && (input.state == "white" || input.state == "red")) {
            let white = input.state == "white";
            check(trim(fs.readfile(active.leds + "/wan/brightness")) == (white ? "9" : "0"), "Wrong white LED level");
            check(trim(fs.readfile(active.leds + "/wan-error/brightness")) == (white ? "0" : "9"), "Wrong red LED level");
            check(trim(read_control(active.leds + "/wan/trigger")) == (white ? "[netdev]" : "[none]"), "Wrong white LED trigger");
        }
        if (input.repeat) {
            let before = active.writes;
            check(reconcile_wan_led(ctx, false).changed == 0 && active.writes == before, "Repeat reconciliation rewrote controls");
            lock_released(ctx.paths.lock);
        }
    }
    return { name: input.name, state: result == null ? null : result.state, writes: active.writes, route_queries: active.routes };
}

try {
    if (length(ARGV) == 1 && ARGV[0] == "--help") {
        print("Usage: ucode -L MODULE_PATH test_wan_led_native.uc --root /tmp/ac86u-wan-fixture-UNIQUE\n",
            "Creates a fresh private fixture tree; never overwrites it. Retains JSON and filesystem evidence.\n",
            "Uses native ucode/fs/locks with injected link/route snapshots and UCI; no hardware or netlink calls.\n",
            "Adapts active-trigger readback and detach brightness clearing, not LED hardware or event delivery.\n");
        exit(0);
    }
    check(length(ARGV) == 2 && ARGV[0] == "--root", "Expected --root; see --help");
    check(type(rtnl_constants) == "object", "Installed rtnl.const namespace is unavailable");
    let required = ["RTM_GETLINK", "RTM_GETROUTE", "NLM_F_DUMP", "AF_INET", "AF_INET6"];
    for (let i = 0; i < length(required); i++)
        check(type(rtnl_constants[required[i]]) == "int", "Missing native rtnl constant: " + required[i]);
    let root = ARGV[1];
    check(type(root) == "string" && match(root, /^\/tmp\/ac86u-wan-fixture-[A-Za-z0-9_-]+$/), "Unsafe fixture root");
    check(fs.mkdir(root, 448), "Fixture root already exists or cannot be created");
    let cases = [
        { name: "no-carrier-priority", links: [{ ifname: "wan", carrier: false, flags: 1 }], route_error: true, lit: true, no_routes: true, state: "off" },
        { name: "no-route", state: "red", repeat: true },
        { name: "red-detach-reapplies-maximum", red_trigger: "default-on", red_lit: true, state: "red", repeat: true },
        { name: "ipv4-default", v4: [{ family: 2, table: 254, type: 1 }], state: "white", repeat: true },
        { name: "ipv6-default", v6: [{ family: 10, table: 254, type: 1, dst: "::/0" }], state: "white" },
        { name: "nondefault-route", v4: [{ family: 2, table: 254, type: 1, dst: "0.0.0.0/1" }], state: "red" },
        { name: "other-table", v4: [{ family: 2, table: 100, type: 1 }], state: "red" },
        { name: "non-unicast", v4: [{ family: 2, table: 254, type: 6 }], state: "red" },
        { name: "masked-link-flags", links: [{ ifname: "wan", carrier: true, flags: [1, 1] }], state: "red" },
        { name: "boot-owned", boot: "released=0 panic=0\n", state: "held", no_write: true, no_routes: true },
        { name: "panic-owned", boot: "released=1 panic=1\n", state: "held", no_write: true, no_routes: true },
        { name: "custom-brightness", custom: ["brightness", "3"], state: "overridden", no_write: true },
        { name: "custom-red", custom_red: true, state: "overridden", no_write: true },
        { name: "alloff-over-custom", custom_red: true, alloff: true, lit: true, state: "user_off" },
        { name: "dry-run", dryrun: true, state: "red", no_write: true },
        { name: "route-query-error", route_error: true, error: true },
        { name: "malformed-carrier", links: [{ ifname: "wan", carrier: "false", flags: 1 }], error: true },
        { name: "malformed-route", v4: [{ family: 2, type: 1 }], error: true },
        { name: "unsafe-lock-leaf", unsafe: "leaf", error: true },
        { name: "unsafe-lock-ancestor", unsafe: "ancestor", error: true },
        { name: "nonprivate-lock-parent", unsafe: "parent", error: true },
        { name: "other-board", other_board: true, state: "not_applicable", no_write: true, no_routes: true }
    ];
    let report = { root, passed: 0, failed: 0, cases: [] };
    for (let i = 0; i < length(cases); i++) {
        try { push(report.cases, run_case(cases[i], root, i)); report.passed++; }
        catch (error) { push(report.cases, { name: cases[i].name, error: "" + error }); report.failed++; }
        warn("[native-wan-fixture] " + cases[i].name + ": " + (report.cases[i].error == null ? "PASS" : "FAIL") + "\n");
    }
    let encoded = sprintf("%J\n", report);
    save(root + "/report.json.tmp", encoded);
    check(fs.rename(root + "/report.json.tmp", root + "/report.json"), "Cannot publish fixture report");
    print(encoded);
    exit(report.failed ? 1 : 0);
} catch (error) {
    warn("[test_wan_led_native] FAILED: " + error + "\n");
    exit(2);
}

// <FILE>contrib/ac86u/tests/test_wan_led_native.uc</FILE> - <DESC>Exercise WAN reconciliation in native ucode with isolated real filesystem controls.</DESC>
// <VERS>END OF VERSION: 0.1.4</VERS>
