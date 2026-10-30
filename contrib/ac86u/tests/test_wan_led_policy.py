# <FILE>contrib/ac86u/tests/test_wan_led_policy.py</FILE> - <DESC>Exercise carrier/route WAN policy and guarded idempotent LED effects.</DESC>
# <VERS>VERSION: 0.1.5</VERS>
# <WCTX>Keep WAN indicators consistent across boot release, link events and installed default-route changes.</WCTX>
# <CLOG>Port the focused hardware regression to native OpenWrt source paths.</CLOG>

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
MODULES = ROOT / "target/linux/bcm4908/base-files/usr/share/ac86u"
HARNESS = r"""
const fixture = JSON.parse(process.argv[1]);
const files = {
  '/proc/self/stat': '123 (ucode) S 1 1\n',
  '/board': 'asus,rt-ac86u\n', '/boot': 'released=1 panic=0\n',
  '/led/wan/trigger': '[none] netdev\n', '/led/wan/brightness': '0\n',
  '/led/wan/max_brightness': '9\n', '/led/wan/device_name': '\n',
  '/led/wan/link': '0\n', '/led/wan/rx': '0\n', '/led/wan/tx': '0\n',
  '/led/wan-error/trigger': '[none] netdev\n',
  '/led/wan-error/brightness': '0\n', '/led/wan-error/max_brightness': '9\n',
  ...fixture.files
};
const writes = [], calls = [], locks = [];
const pathStats = {'/tmp':{type:'directory',uid:0,mode:1023},
 '/tmp/private':{type:'directory',uid:0,mode:448},...fixture.path_stats};
const type = x => x == null ? 'null' : Array.isArray(x) ? 'array' :
  typeof x === 'number' ? (Number.isInteger(x) ? 'int' : 'double') : typeof x;
const length = x => x == null ? 0 : typeof x === 'object' && !Array.isArray(x) ? Object.keys(x).length : x.length;
const keys = Object.keys, trim = x => x.trim(), split = (x,s) => x.split(s);
const join = (s,x) => x.join(s), sort = x => x.sort(), int = x => parseInt(x,10);
const push = (x,...v) => x.push(...v);
const substr = (x,a,n) => n == null ? x.substr(a) : x.substr(a,n);
const match = (x,p) => x.match(p), index = (x,v) => x.indexOf(v);
const die = x => { throw new Error(x); }, sleep = () => {};
const fs = {
  readfile(p) { return Object.hasOwn(files,p) ? files[p] : null; },
  stat(p) { return Object.hasOwn(files,p) ? {type:'file'} : null; },
  lstat(p) {return Object.hasOwn(pathStats,p)?pathStats[p]:Object.hasOwn(files,p)?{type:'file',uid:0,mode:384}:null;},
  dirname(p) {return require('path').posix.dirname(p);},
  realpath(p) {return fixture.realpaths?.[p]??(this.lstat(p)?p:null);},
  mkdir(p,mode) {calls.push('mkdir:'+p);pathStats[p]={type:'directory',uid:0,mode};return true;},
  open(p) { calls.push('open:'+p); return {
    lock(op) { locks.push(op); return fixture.lock_fail ? null : true; },
    close() { calls.push('close'); return true; }
  }; },
  writefile(p,v) {
    if (fixture.write_fail === p) return null;
    writes.push([p,v]);
    if (p.endsWith('/trigger')) {
      if (!(files[p]||'').includes('[none]')) files[p.slice(0,-8)+'/brightness']='0\n';
      files[p] = '['+trim(v)+'] none netdev\n';
      if (trim(v) === 'netdev') {
        let d=p.slice(0,-8);
        for (const k of ['device_name','link','rx','tx']) files[d+'/'+k] ??= k==='device_name'?'\n':'0\n';
      }
    } else files[p] = v;
    return v.length;
  }, error() { return 'fixture I/O failure'; }
};
const system = fixture.system || {};
const cursor = { unload() {}, load() { return !fixture.uci_fail; }, get_all() {return system;} };
const r = {
  const:{RTM_GETLINK:18, RTM_GETROUTE:26, NLM_F_DUMP:768, AF_INET:2, AF_INET6:10},
  request(cmd, flags, payload) {
    if (![18,26].includes(cmd) || flags!==768 || (cmd===26 && ![2,10].includes(payload.family)))
      throw new Error('Invalid rtnl adapter request');
    calls.push({cmd,flags,payload});
    if (fixture.snapshot_fail) return null;
    if (cmd===18) return fixture.links ?? [];
    if (fixture.route_fail) return null;
    return payload.family===2 ? (fixture.v4 ?? []) : (fixture.v6 ?? []);
  }, error() { return 'fixture rtnl failure'; }
};
const ctx = {fs, r, cursor, paths:{board:'/board',boot:'/boot',sysfs:'/led',lock:fixture.lockpath||'/tmp/private/lock'}};
let result, error;
try {
  if (fixture.pure) result=wan_led_snapshot(fixture.links, fixture.routes);
  else {
    result=reconcile_wan_led(ctx,!!fixture.dry_run);
    if (fixture.twice) { writes.length=0; result=reconcile_wan_led(ctx,false); }
  }
} catch(e) {error=String(e.message||e);}
console.log(JSON.stringify({result,error,writes,calls,locks,files}));
"""


@unittest.skipUnless(
    shutil.which("node"), "Node is required for the boundary simulator"
)
class WanLedPolicyTests(unittest.TestCase):
    def execute(self, fixture):
        source = ""
        for name in (
            "col_wan_led_policy.uc",
            "fnc_wan_led_runtime_path.uc",
            "fnc_apply_wan_led.uc",
            "fnc_reconcile_wan_led.uc",
        ):
            text = (MODULES / name).read_text()
            source += "\n".join(
                line.replace("export ", "", 1)
                for line in text.splitlines()
                if not line.startswith("import ")
            )
        insertion = HARNESS.index("let result, error;")
        program = HARNESS[:insertion] + source + "\n" + HARNESS[insertion:]
        result = subprocess.run(
            ["node", "-e", program, json.dumps(fixture)],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)

    def monitor(self, fixture):
        harness = HARNESS[: HARNESS.index("const ctx =")]
        source = ""
        for name in (
            "col_wan_led_policy.uc",
            "fnc_wan_led_runtime_path.uc",
            "fnc_apply_wan_led.uc",
            "fnc_reconcile_wan_led.uc",
            "orc_wan_led_monitor.uc",
        ):
            source += "\n" + "\n".join(
                line.replace("export ", "", 1)
                for line in (MODULES / name).read_text().splitlines()
                if not line.startswith("import ")
            )
        simulation = r"""
const handlers={}, output=[];
let callback=null, timerCallback=null;
const getenv = k => ({AC86U_WAN_LED_MODE:'watch',AC86U_WAN_LED_SYSFS:'/led',
 AC86U_WAN_LED_BOARD_FILE:'/board',AC86U_WAN_LED_BOOT_STATUS:'/boot',
 AC86U_WAN_LED_LOCK:'/tmp/private/lock',AC86U_WAN_LED_STATUS:'/tmp/private/status',...fixture.env})[k] ?? null;
const sprintf = (format,value) => JSON.stringify(value)+'\n';
const printf = (format,value) => output.push(JSON.stringify(value));
const warn = text => output.push(text), time = () => 1793210000;
const signal = () => {throw new Error('Monitor must use event-loop signal resources');};
const exit = code => {throw {exitCode:code};};
const uci={cursor:()=>cursor};
fs.rename=(a,b)=>{files[b]=files[a];delete files[a];calls.push('rename');return true;};
Object.assign(r.const,{RTM_NEWLINK:16,RTM_DELLINK:17,RTM_NEWROUTE:24,RTM_DELROUTE:25,
 RTNLGRP_LINK:1,RTNLGRP_IPV4_ROUTE:7,RTNLGRP_IPV6_ROUTE:11});
r.listener=function(cb,commands,groups){
 if(JSON.stringify(commands)!=='[16,17,24,25]' || JSON.stringify(groups)!=='[1,7,11]')
   throw new Error('Invalid rtnl subscription constants');
 calls.push({subscribe:{commands,groups}});callback=cb;return{close(){calls.push('watcher_closed');}};
};
const loop={init(){calls.push('loop_init');},error(){return 'fixture loop';},
 signal(name,fn){calls.push('loop_signal:'+name);handlers[name]=fn;return{delete(){calls.push('signal_deleted:'+name);}};},
 timer(ms,cb){timerCallback=cb;return{set(){calls.push('heartbeat_set');},cancel(){calls.push('heartbeat_cancel');}};},
 run(){callback();if(fixture.heartbeat)timerCallback();handlers.TERM();},
 end(){calls.push('loop_end');},done(){calls.push('loop_done');}};
let exitCode=0;
try {
"""
        program = (
            harness
            + simulation
            + source
            + r"""
} catch(error) {exitCode=error.exitCode??99;output.push(String(error.message||error));}
console.log(JSON.stringify({exitCode,output,writes,calls,locks,files}));
"""
        )
        result = subprocess.run(
            ["node", "-e", program, json.dumps(fixture)],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)

    def test_carrier_priority_and_default_routes(self):
        for carrier, routes, expected in (
            (False, [], "off"),
            (False, [{"family": 2, "table": 254, "type": 1}], "off"),
            (True, [], "red"),
            (True, [{"family": 2, "table": 254, "type": 1}], "white"),
            (True, [{"family": 10, "table": 254, "type": 1, "dst": "::/0"}], "white"),
        ):
            with self.subTest(carrier=carrier, routes=routes):
                result = self.execute(
                    {
                        "pure": True,
                        "links": [{"ifname": "wan", "carrier": carrier, "flags": 1}],
                        "routes": routes,
                    }
                )
                self.assertNotIn("error", result)
                self.assertEqual(result["result"]["state"], expected)

    def test_route_selection_and_link_flags(self):
        invalid = [
            {"family": 2, "table": 100, "type": 1},
            {"family": 2, "table": 254, "type": 6},
            {"family": 2, "table": 254, "type": 1, "dst": "0.0.0.0/1"},
            {"family": 10, "table": 254, "type": 1, "dst": "::/64"},
        ]
        result = self.execute(
            {
                "pure": True,
                "links": [{"ifname": "wan", "carrier": True, "flags": [1, 1]}],
                "routes": invalid,
            }
        )
        self.assertEqual(result["result"]["state"], "red")
        for links in ([], [{"ifname": "wan", "carrier": True, "flags": 0}]):
            self.assertEqual(
                self.execute({"pure": True, "links": links, "routes": []})["result"][
                    "state"
                ],
                "off",
            )

    def test_logical_up_does_not_override_physical_down(self):
        result = self.execute(
            {
                "logical_up": True,
                "links": [{"ifname": "wan", "carrier": False, "flags": 1}],
                "v4": [{"family": 2, "table": 254, "type": 1}],
            }
        )
        self.assertEqual(result["result"]["state"], "off")

    def test_release_and_panic_hold_without_writes(self):
        for boot in ("released=0 panic=0\n", "released=1 panic=1\n"):
            result = self.execute({"files": {"/boot": boot}})
            self.assertEqual(result["result"]["state"], "held")
            self.assertEqual(result["writes"], [])

    def test_user_off_and_override(self):
        result = self.execute(
            {
                "system": {"cfg": {".type": "system", "leds_off": "1"}},
                "files": {"/led/wan/brightness": "9\n"},
            }
        )
        self.assertEqual(result["result"]["state"], "user_off")
        self.assertEqual(result["files"]["/led/wan/brightness"], "0\n")
        custom = {
            "led_custom": {".type": "led", "sysfs": "wan-error", "trigger": "timer"}
        }
        result = self.execute({"system": custom})
        self.assertEqual(result["result"]["state"], "overridden")
        self.assertEqual(result["writes"], [])
        for option in ("brightness", "interval", "invert"):
            custom = {
                "white": {
                    ".type": "led",
                    "sysfs": "wan",
                    "trigger": "netdev",
                    "dev": "wan",
                    "mode": "link tx rx",
                    option: "3",
                }
            }
            self.assertEqual(
                self.execute({"system": custom})["result"]["state"], "overridden"
            )

    def test_white_stock_mapping_and_idempotence(self):
        fixture = {
            "links": [{"ifname": "wan", "carrier": True, "flags": 1}],
            "v4": [{"family": 2, "table": 254, "type": 1}],
            "system": {
                "led_wan": {
                    ".type": "led",
                    "sysfs": "wan",
                    "trigger": "netdev",
                    "dev": "wan",
                    "mode": "link tx rx",
                }
            },
        }
        result = self.execute(fixture)
        self.assertEqual(result["result"]["state"], "white")
        self.assertIn("[netdev]", result["files"]["/led/wan/trigger"])
        fixture["twice"] = True
        self.assertEqual(self.execute(fixture)["writes"], [])

    def test_red_disables_white_before_enabling_warning(self):
        result = self.execute(
            {
                "links": [{"ifname": "wan", "carrier": True, "flags": 1}],
                "files": {"/led/wan/brightness": "9\n"},
            }
        )
        self.assertEqual(result["result"]["state"], "red")
        self.assertLess(
            result["writes"].index(["/led/wan/brightness", "0\n"]),
            result["writes"].index(["/led/wan-error/brightness", "9\n"]),
        )

    def test_red_reasserts_level_after_old_trigger_detaches(self):
        fixture = {
            "links": [{"ifname": "wan", "carrier": True, "flags": 1}],
            "files": {
                "/led/wan-error/trigger": "none [timer] netdev\n",
                "/led/wan-error/brightness": "9\n",
            },
        }
        result = self.execute(fixture)
        self.assertNotIn("error", result)
        self.assertEqual(result["files"]["/led/wan-error/brightness"], "9\n")
        self.assertIn("[none]", result["files"]["/led/wan-error/trigger"])
        self.assertLess(
            result["writes"].index(["/led/wan-error/trigger", "none\n"]),
            result["writes"].index(["/led/wan-error/brightness", "9\n"]),
        )
        fixture["twice"] = True
        self.assertEqual(self.execute(fixture)["writes"], [])

    def test_white_reasserts_level_after_old_trigger_detaches(self):
        fixture = {
            "links": [{"ifname": "wan", "carrier": True, "flags": 1}],
            "v4": [{"family": 2, "table": 254, "type": 1}],
            "files": {
                "/led/wan/trigger": "none [timer] netdev\n",
                "/led/wan/brightness": "9\n",
            },
        }
        result = self.execute(fixture)
        self.assertNotIn("error", result)
        self.assertEqual(result["files"]["/led/wan/brightness"], "9\n")
        self.assertIn("[netdev]", result["files"]["/led/wan/trigger"])
        fixture["twice"] = True
        self.assertEqual(self.execute(fixture)["writes"], [])

    def test_stock_mode_tokens_use_native_join_contract(self):
        for mode in ("rx link tx", ["tx", "link", "rx"]):
            with self.subTest(mode=mode):
                fixture = {
                    "links": [{"ifname": "wan", "carrier": True, "flags": 1}],
                    "v4": [{"family": 2, "table": 254, "type": 1}],
                    "system": {
                        "white": {
                            ".type": "led",
                            "sysfs": "wan",
                            "trigger": "netdev",
                            "dev": "wan",
                            "mode": mode,
                        }
                    },
                }
                result = self.execute(fixture)
                self.assertNotIn("error", result)
                self.assertEqual(result["result"]["state"], "white")

    def test_dry_run_no_mutation_and_other_board_noop(self):
        result = self.execute({"dry_run": True})
        self.assertEqual(result["writes"], [])
        self.assertNotIn("open:/tmp/private/lock", result["calls"])
        result = self.execute({"files": {"/board": "other,board\n"}})
        self.assertEqual(result["result"]["state"], "not_applicable")
        self.assertEqual(result["calls"], [])

    def test_failures_do_not_become_missing_route(self):
        result = self.execute({"snapshot_fail": True})
        self.assertIn("error", result)
        self.assertEqual(result["writes"], [])
        self.assertEqual(result["locks"], ["xn", "u"])
        result = self.execute(
            {
                "links": [{"ifname": "wan", "carrier": True, "flags": 1}],
                "write_fail": "/led/wan-error/brightness",
            }
        )
        self.assertIn("error", result)
        self.assertEqual(result["locks"][-1], "u")

    def test_no_carrier_does_not_need_a_route_query(self):
        result = self.execute({"route_fail": True})
        self.assertNotIn("error", result)
        self.assertEqual(result["result"]["state"], "off")
        self.assertIsNone(result["result"]["has_default"])
        self.assertFalse(
            any(
                isinstance(call, dict) and call.get("cmd") == 26
                for call in result["calls"]
            )
        )
        result = self.execute(
            {
                "links": [{"ifname": "wan", "carrier": True, "flags": 1}],
                "route_fail": True,
            }
        )
        self.assertIn("error", result)
        self.assertEqual(result["writes"], [])

    def test_monitor_subscribes_before_snapshot_and_heartbeat_does_not_poll(self):
        result = self.monitor({"heartbeat": True})
        self.assertEqual(result["exitCode"], 0, result["output"])
        subscription = next(
            i
            for i, call in enumerate(result["calls"])
            if isinstance(call, dict) and "subscribe" in call
        )
        snapshot = next(
            i
            for i, call in enumerate(result["calls"])
            if isinstance(call, dict) and "cmd" in call
        )
        self.assertLess(subscription, snapshot)
        self.assertEqual(
            result["calls"][subscription]["subscribe"]["groups"], [1, 7, 11]
        )
        self.assertEqual(
            sum(
                isinstance(call, dict) and call.get("cmd") == 18
                for call in result["calls"]
            ),
            2,
        )
        status = json.loads(result["files"]["/tmp/private/status"])
        self.assertEqual(status["stage"], "complete")
        self.assertEqual(status["event_count"], 1)
        self.assertEqual(status["pid"], 123)
        self.assertEqual(status["updated_utc"], 1793210000)
        self.assertNotIn("watcher_closed", result["calls"])
        self.assertEqual(
            sorted(
                call
                for call in result["calls"]
                if isinstance(call, str) and call.startswith("signal_deleted:")
            ),
            ["signal_deleted:HUP", "signal_deleted:INT", "signal_deleted:TERM"],
        )

    def test_monitor_records_failed_snapshot_terminal(self):
        result = self.monitor({"snapshot_fail": True})
        self.assertEqual(result["exitCode"], 1)
        status = json.loads(result["files"]["/tmp/private/status"])
        self.assertEqual(status["stage"], "failed")
        self.assertIn("error", status)

    def test_second_monitor_preserves_existing_owner_status(self):
        existing = '{"pid":999,"stage":"running"}\n'
        result = self.monitor(
            {"lock_fail": True, "files": {"/tmp/private/status": existing}}
        )
        self.assertEqual(result["exitCode"], 1)
        self.assertEqual(result["files"]["/tmp/private/status"], existing)
        self.assertFalse(
            any(
                isinstance(call, dict) and "subscribe" in call
                for call in result["calls"]
            )
        )

    def test_runtime_paths_reject_untrusted_parents_and_symlink_leaves(self):
        for info in (
            {"type": "link", "uid": 0, "mode": 448},
            {"type": "directory", "uid": 1000, "mode": 448},
            {"type": "directory", "uid": 0, "mode": 511},
        ):
            with self.subTest(info=info):
                result = self.execute({"path_stats": {"/tmp/private": info}})
                self.assertIn("error", result)
                self.assertEqual(result["writes"], [])
                self.assertNotIn("open:/tmp/private/lock", result["calls"])
        result = self.execute({"realpaths": {"/tmp/private": "/etc/private"}})
        self.assertIn("error", result)
        result = self.execute(
            {
                "path_stats": {
                    "/tmp/private/lock": {"type": "link", "uid": 0, "mode": 384}
                }
            }
        )
        self.assertIn("error", result)
        result = self.execute(
            {
                "lockpath": "/tmp/link/private/lock",
                "path_stats": {
                    "/tmp/link": {"type": "link", "uid": 0, "mode": 448},
                    "/tmp/link/private": {"type": "directory", "uid": 0, "mode": 448},
                },
            }
        )
        self.assertIn("error", result)
        self.assertEqual(result["writes"], [])

    def test_private_runtime_creation_is_not_a_dry_run_side_effect(self):
        fixture = {"path_stats": {"/tmp/private": None}}
        result = self.execute(dict(fixture, dry_run=True))
        self.assertNotIn("error", result)
        self.assertNotIn("mkdir:/tmp/private", result["calls"])
        result = self.execute(fixture)
        self.assertNotIn("error", result)
        self.assertIn("mkdir:/tmp/private", result["calls"])

    def test_launcher_help_invalid_mode_and_dry_run_dispatch(self):
        launcher = ROOT / "target/linux/bcm4908/base-files/usr/libexec/ac86u-wan-led"
        help_result = subprocess.run(
            ["sh", str(launcher), "--help"], capture_output=True, text=True
        )
        self.assertEqual(help_result.returncode, 0)
        self.assertIn("--dry-run", help_result.stdout)
        invalid = subprocess.run(
            ["sh", str(launcher), "--bad"], capture_output=True, text=True
        )
        self.assertEqual(invalid.returncode, 2)
        with tempfile.TemporaryDirectory() as temporary:
            fake = Path(temporary) / "ucode"
            fake.write_text(
                "#!/usr/bin/env python3\nimport json,os,sys\nprint(json.dumps({'argv':sys.argv[1:],'mode':os.environ['AC86U_WAN_LED_MODE']}))\n"
            )
            fake.chmod(0o755)
            environment = dict(
                os.environ,
                AC86U_WAN_LED_LIBDIR=str(MODULES),
                AC86U_WAN_LED_UCODE=str(fake),
            )
            result = subprocess.run(
                ["sh", str(launcher), "--dry-run"],
                env=environment,
                capture_output=True,
                text=True,
                check=True,
            )
            output = json.loads(result.stdout)
            self.assertEqual(output["mode"], "dry-run")
            self.assertEqual(
                output["argv"],
                ["-L", str(MODULES), str(MODULES / "orc_wan_led_monitor.uc")],
            )


if __name__ == "__main__":
    unittest.main()

# <FILE>contrib/ac86u/tests/test_wan_led_policy.py</FILE> - <DESC>Exercise carrier/route WAN policy and guarded idempotent LED effects.</DESC>
# <VERS>END OF VERSION: 0.1.5</VERS>
