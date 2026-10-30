// <FILE>target/linux/bcm4908/base-files/usr/share/ac86u/fnc_reconcile_wan_led.uc</FILE> - <DESC>Serialize one current-state WAN LED reconciliation with board and ownership guards.</DESC>
// <VERS>VERSION: 0.1.3</VERS>
// <WCTX>Share one carrier/route policy between boot handoff, hotplug and the event monitor.</WCTX>
// <CLOG>Validate private canonical RAM lock paths before opening a serialized reconciliation.</CLOG>

import { wan_led_snapshot, wan_led_overrides } from "col_wan_led_policy";
import { apply_wan_led } from "fnc_apply_wan_led";
import { wan_led_runtime_path } from "fnc_wan_led_runtime_path";

export function reconcile_wan_led(ctx, dry_run) {
    let board = ctx.fs.readfile(ctx.paths.board);
    if (type(board) != "string") die("Cannot read WAN policy board identity");
    if (trim(board) != "asus,rt-ac86u") return { state: "not_applicable", changed: 0 };
    let lock = null, locked = false, result = null, failure = null;
    try {
        wan_led_runtime_path(ctx.fs, ctx.paths.lock, dry_run);
        if (!dry_run) {
            lock = ctx.fs.open(ctx.paths.lock, "a");
            if (!lock) die("Cannot open WAN policy lock");
            for (let attempt = 0; attempt < 100 && !locked; attempt++) {
                locked = lock.lock("xn") == true;
                if (!locked) sleep(50);
            }
            if (!locked) die("WAN policy lock timed out");
        }
        let held = false;
        if (ctx.fs.stat(ctx.paths.boot)) {
            let boot = ctx.fs.readfile(ctx.paths.boot);
            if (type(boot) != "string") die("Cannot read boot LED ownership");
            let tokens = split(trim(boot), /\s+/);
            if (index(tokens, "released=0") < 0 && index(tokens, "released=1") < 0)
                die("Invalid boot LED ownership state");
            held = index(tokens, "released=1") < 0 || index(tokens, "panic=1") >= 0;
        }
        if (held) result = { state: "held", changed: 0 };
        else {
            ctx.cursor.unload("system");
            if (!ctx.cursor.load("system")) die("Cannot load system LED configuration");
            let overrides = wan_led_overrides(ctx.cursor.get_all("system"));
            if (overrides.user_off)
                result = { state: "user_off", changed: dry_run ? 0 : apply_wan_led(ctx, "off") };
            else if (overrides.overridden) result = { state: "overridden", changed: 0 };
            else {
                let links = ctx.r.request(ctx.r.const.RTM_GETLINK, ctx.r.const.NLM_F_DUMP, {});
                if (links == true) links = [];
                if (type(links) != "array") die("WAN link snapshot failed: " + ctx.r.error());
                result = wan_led_snapshot(links, []);
                if (result.carrier) {
                    let routes = [], families = [ctx.r.const.AF_INET, ctx.r.const.AF_INET6];
                    for (let i = 0; i < length(families); i++) {
                        let family = ctx.r.request(ctx.r.const.RTM_GETROUTE, ctx.r.const.NLM_F_DUMP, { family: families[i] });
                        if (family == true) family = [];
                        if (type(family) != "array") die("Default route snapshot failed: " + ctx.r.error());
                        for (let n = 0; n < length(family); n++) push(routes, family[n]);
                    }
                    result = wan_led_snapshot(links, routes);
                    result.route_checked = true;
                }
                else { result.has_default = null; result.route_checked = false; }
                result.changed = dry_run ? 0 : apply_wan_led(ctx, result.state);
            }
        }
    } catch (error) { failure = error; }
    if (locked && lock.lock("u") != true && failure == null) failure = "WAN policy unlock failed";
    if (lock && lock.close() != true && failure == null) failure = "WAN policy lock close failed";
    if (failure != null) die(failure);
    return result;
};

// <FILE>target/linux/bcm4908/base-files/usr/share/ac86u/fnc_reconcile_wan_led.uc</FILE> - <DESC>Serialize one current-state WAN LED reconciliation with board and ownership guards.</DESC>
// <VERS>END OF VERSION: 0.1.3</VERS>
