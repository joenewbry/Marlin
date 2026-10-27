# Experimental LLM prompt control on S1 Pro v040

This candidate starts at ThomasToka/Marlin release source v040
(`0114371a8644ab58e254865f2c0345b061704b39`), not the generic development
branch. It is a separate lineage from the earlier Creality .24F4 experiment.
Neither candidate has been flashed or qualified for printing.

## Build and native checks

```
pio run -e STM32F401RC_creality_e3s1pro_llm -j 2
python3 buildroot/tests/llm_prompt_native.py
```

These commands compile and test locally. They do not upload firmware or open
any printer. The profile extends the release's S1 Pro bilinear-leveling profile,
removes laser support, and enables `LLM_PROMPT_PROTOCOL`. Input shaping on X/Y,
leveling, preview and thermal protection remain enabled. This configuration is
an engineering candidate: its F401RC target, boot offset, pins, screen firmware,
probe geometry, thermal settings and stored settings still require physical
qualification. Do not copy old EEPROM contents into this release unqualified.

The protocol's STM32 UART1 receive integration requires the non-DMA path. A
compile-time guard rejects other transport configurations. Other profiles do
not enable the new wire protocol by default.

## Implemented prompt behavior

Versioned unnumbered `M876 V1` frames use a session token, prompt generation,
request ID and choice index. Inspect is read-only; bind establishes one session
per firmware boot; respond applies only to the current shown prompt. Receipts
are distinct from ordinary G-code `ok`. Duplicate requests return the cached
result without repeating an action. A receipt proves handler acceptance, not
physical recovery or completion of motion.

The interrupt path collects bounded input and defers responses to `idle()`.
Exact protocol frames bypass the ordinary command ring; the emergency parser
still sees original bytes. Both the emergency parser and ordinary dispatcher
fence legacy `M108` after protocol binding or while protocol input is pending.
Legacy `M876` responses are handled only through the deferred mailbox when the
emergency parser is enabled, preventing duplicate and unguarded dispatch.

Wire-v1 reason IDs remain 0/1/2/3/4 for none/runout/user wait/pause resume/info,
although the newer internal enum has an inserted reheat reason. Runout reheat
is intentionally unsupported and advertised as 0xff, so existing hosts fail
closed. Do not treat it as pause resume. Active runout cannot be disabled or
cleared by a remote continue response. Screen/timeout cleanup invalidates
prompt identity; a reply for a previous prompt cannot release a replacement.

## Pause and resume limits

This firmware protocol handles supported user prompts. The host owns stopping
and continuing a streamed job, with separate receipts and position/state
checks. Replying to a prompt is not a job-resume guarantee. A powered pause may
retain position but requires actual motion, temperature and material tests.
Process restart, disconnection, power loss and cooled overnight resume remain
unqualified; no automatic recovery from heater/sensor faults is implemented.

## Validation boundaries

Native tests compile the actual HostUI, wire, emergency parser, M876 and M108
sources with stubbed hardware. They cover authority, stale prompts, runout,
strict legacy suffixes, reason mapping, router behavior and emergency flags.
Existing host channel/backend tests can exercise this native executable through
pipes. They do not qualify real interrupt timing, the touch screen, heaters,
movement, physical pause/resume or settings restoration. The development
printer has an unresolved invalid nozzle reading; commissioning is deferred.
The other printer remains protected. Camera work is deferred by the owner.

Review overview: https://robot.digitalsurfacelabs.com/pages/creality-for-llm/

Originating session title was unavailable; session thread
01a17442-1b53-7313-9ab2-b0ca21e2918b.

## Heater watch parity backport

This layer carries the earlier experiment's two HeaterWatch fixes onto v040:
zero remains the disabled sentinel even when a deadline wraps, and watching
continues until the runaway protection threshold takes over. Hotend, bed and
chamber watch typedefs use their respective thermal-protection hysteresis.
No configured watch periods or temperature limits are changed. The cooler
specialization is untouched; no cooler qualification is claimed.

```
python3 buildroot/tests/llm_heater_watch_native.py
```

The original template fails the zero-deadline assertion. The corrected template
passes six synthetic-clock scenarios and three actual typedef checks. These
checks cover arming, expiry, wrap and handoff thresholds; full manager fault
shutdown and physical heaters have not been qualified on this source baseline.
The earlier Creality-native thermal results do not transfer automatically.

## Complete the runtime handoff

The prior layer copied the watch template and threshold typedefs, but v040's
runaway state machine still waited for the exact target. An actual-source
runtime harness reproduced six failures: at/above the handoff threshold the
watch disarmed, while stable protection never started. A later drop could then
remain undetected by those two branches. This candidate includes the missing
runtime change from [Marlin PR #28695](https://github.com/MarlinFirmware/Marlin/pull/28695)
(merged commit `c27424fa51053dd3b0febde2f03b287499403d39`): enter stable protection
at the same hysteresis boundary. Watch periods and limits are unchanged.

```
python3 buildroot/tests/llm_thermal_paths_native.py
```

All 32 cases pass for extracted actual watch/runaway/error/disable/loud-kill
paths with recording IO. The native build includes both hotend/bed protections,
autotemp, idle-handler, screen-fault, beeper and nozzle-park branches. Assertions
check targets, PWM and pin writes are zero before park or final kill; an unhomed
machine does not park; repeated faults disable outputs again without repeating
kill. Near-target hold/drop, initial heating stalls, timer wrap, idle timeout
and normal heating are included. The 32-case harness is separate from the six
watch-template cases and the eleven prompt cases.

These are synthetic sensor/clock inputs, recording HAL/target/serial/screen/
buzzer/park/planner/kill dependencies, and isolated actual source functions.
They do not execute the full temperature task, ADC, interrupts, PID output,
real motion/kill or physical heaters. No broader physical qualification follows
from these results. The earlier 7569d4a layer requires this dependent correction
before commissioning consideration; none has been flashed.

## Read-only machine variables

The LLM profile additionally enables `LLM_MACHINE_STATE`, advertised by M115 as
`Cap:LLM_MACHINE_STATE:1`. Other profiles leave it disabled. After session binding,
`M876 V1 I Q<request>` emits the existing prompt receipt followed by one
`//llmstate:v2` line with the same request and bound session. The state line is
299 ASCII bytes before LF. Unbound inspection, binding, responding, malformed
commands and exhausted state sequence produce no state line. Inspecting again
samples again, even when the inspect request number is repeated; reads do not
repeat a machine action. The host's journal still deduplicates its tool requests.

Fields, in canonical order:

```
//llmstate:v2 Q<8> T<32> N<8> U<8> F<2> H<2> K<2> E<2> B<2> R<2> A<2> P<32> O<24> D<24> V<72> I<24> C<2> J<2>
```

All widths are lowercase hexadecimal digits. Q is request, T is session, N is a
nonzero sequence that saturates instead of wrapping, U is the wrapping uint32
millisecond uptime. F bits are firmware `isRunning`, user wait, heat wait and
leveling active. H/K are XYZ homed/trusted masks, E is the XYZE logical enable
mask, B is planner block count, R is the XYZE relative-mode mask, A is tool zero.
P contains four commanded native position floats, O three workspace offsets,
D three home offsets. V contains unit factor, feedrate mm/s, feed/flow percentages,
fan PWM, hotend actual/target, bed actual/target. Each float is its binary32 bit
pattern written as eight hex digits, not an endian-dependent byte dump. Unknown
versions, reserved flag bits or nonfinite values must not authorize host actions.

Version 2 adds I: three uint32 millisecond values (previous_move_ms,
stepper_inactive_time and max_inactive_time), C: XYZE DISABLE_IDLE axis mask,
and J: bit zero for the raw stepper timeout predicate, bit one for the maximum
inactivity predicate, both evaluated at U. With no idle axes, the absent stepper
interval is encoded zero and its predicate is false. The host can distinguish
unsupported from a supported zero interval using C. A supported zero stepper
interval has a true raw predicate; MarlinCore separately checks the nonzero
interval before shutdown. M85 zero disables its maximum-inactivity predicate.
The production three-argument ELAPSED comparison uses unsigned uint32 U-origin
subtraction, including wrap; the report does not count wraps or infer wall time.
No host countdown or actual motor-shutdown guarantee follows. Planner activity,
pause/SD state and no-sleep policy additionally affect timer reset/shutdown;
those full runtime-policy inputs remain outside this report. V1 reports lack
this coverage and must remain explicitly incomplete on the host. The M876
command protocol remains V1; only the separate state schema changes to V2.

The scalar state is copied in one short critical section, then serialized with
interrupts restored. There is no planner synchronization, idle recursion, command
injection, settings change, heater action or movement in the getter. Response
transmission and actual interrupt duration are not physically qualified.

This is controller-variable evidence. Homed/trusted/enable flags are firmware
beliefs, not proof of physical position or motor power. Position is interpreter
position, which may be ahead of queued motion. Zero planner blocks is not an
operation-correlated completion barrier, stepper-idle or physical stop proof.
Temperature sampling age and sensor health are unknown. The report does not
fingerprint firmware/full settings, mesh, probe geometry, material, part continuity
or every optional motion feature. A lost report or killed controller leaves state
unknown; an old observation never establishes current readiness.

Run `python3 buildroot/tests/llm_machine_state_native.py` for the actual getter
and serializer compiled against hardware stubs. It runs eleven existing prompt
cases, five state-wire cases and eight getter configurations including idle-axis support on/off, timer boundaries,
zero intervals, uint32 wrap and values above the signed half-range. Those checks and
an F401 cross-build do not qualify a physical board, display, serial driver,
recovery procedure, motion or heater behavior. No test hook is added to firmware.
