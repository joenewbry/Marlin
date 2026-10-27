"""Compile actual state getter and wire sources with stubbed hardware; never USB."""
from pathlib import Path
import hashlib, json, shutil, subprocess, tempfile
from llm_prompt_native import build_native_harness
ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'Marlin/src'
COMPILER=shutil.which('clang++') or shutil.which('g++')


def compile_run(source, output, *arguments):
    subprocess.run([COMPILER,'-std=gnu++14','-Wall','-Wextra',str(source),'-o',str(output)],check=True)
    return subprocess.check_output([str(output),*arguments],text=True,timeout=5)


def qualify(directory):
    directory=Path(directory)
    wire=directory/'wire'
    original=build_native_harness(wire)
    scenarios=('deferred','invalid_legacy','stale_legacy','bound_legacy','stale','runout','reason_map','accept_once','emergency','router','dispatch_unbound')
    for name in scenarios:subprocess.run([str(original),name],check=True,capture_output=True,text=True,timeout=5)
    main=wire/'main.cpp';content=main.read_text();last=content.rfind('}')
    main.write_text(content[:last]+'return 0;\n'+content[last:])
    config=wire/'inc/MarlinConfigPre.h'
    config.write_text(config.read_text()+'\n#define LLM_MACHINE_STATE 1\n')
    shutil.copy2(SRC/'feature/host_machine_state.h',wire/'feature/host_machine_state.h')
    (wire/'state_main.cpp').write_text(r'''
#define main original_prompt_test_main
#include "main.cpp"
#undef main
#include <limits>
unsigned snapshots=0;
HostMachineState host_machine_state_snapshot() {
 ++snapshots;HostMachineState state{};
 state.uptime=1234;state.flags=15;state.homed=5;state.trusted=1;state.enabled=11;
 state.blocks=7;state.relative=8;state.tool=0;
 for(int i=0;i<4;++i)state.position[i]=float(i)+.25f;
 for(int i=0;i<3;++i){state.workspace[i]=float(i)-2;state.home[i]=float(i)+4;}
 const float values[]={1,12.5f,100,95,128,23.5f,0,22.25f,0};
 for(int i=0;i<9;++i)state.values[i]=values[i];
 return state;
}
void command(const std::string& frame){for(auto c:frame)host_prompt_receive_byte(c);host_prompt_wire_process();}
int main(int argc,char**argv){
 assert(argc==2);const std::string scenario=argv[1];
 if(scenario=="runtime")return original_prompt_test_main(argc,argv);
 command("M876 V1 I Q00000001\n");assert(snapshots==0);
 assert(serial_output.find("//llmstate:")==std::string::npos);serial_output.clear();
 command("M876 V1 B00000000000000000000000000000001 Q00000002\n");
 assert(snapshots==0);serial_output.clear();
 const auto prompt=host_prompt_identity.generation();const bool waiting=marlin.wait_for_user;
 if(scenario=="bound"||scenario=="repeat"){
  command("M876 V1 I Q00000003\n");assert(snapshots==1);
  assert(host_prompt_identity.generation()==prompt&&marlin.wait_for_user==waiting);
  assert(serial_output.find("//llmstate:v1 Q00000003 T00000000000000000000000000000001 N00000001 U000004d2 F0f H05 K01 E0b B07 R08 A00 ")!=std::string::npos);
  if(scenario=="repeat"){serial_output.clear();command("M876 V1 I Q00000003\n");assert(snapshots==2);assert(serial_output.find(" N00000002 ")!=std::string::npos);}
 }
 else if(scenario=="saturation"){
  machine_state_sequence=UINT32_MAX;command("M876 V1 I Q00000003\n");
  assert(snapshots==0&&serial_output.find("//llmstate:")==std::string::npos);
 }
 else if(scenario=="malformed"){
  command("M876 V1 I Q00000000\n");assert(snapshots==0);
  assert(serial_output.find("//llmstate:")==std::string::npos);
 }
 else if(scenario=="response"){
  command("M876 V1 R00000000000000000000000000000001 P00000001 S00 Q00000003\n");
  assert(snapshots==0&&serial_output.find("//llmstate:")==std::string::npos);
 }
 else return 3;
 std::cout<<serial_output;
}
''')
    binary=wire/'state-actions'
    subprocess.run([COMPILER,'-std=gnu++14','-Wall','-Wextra',str(wire/'state_main.cpp'),'-o',str(binary)],check=True)
    for name in ('bound','repeat','saturation','malformed','response'):
        output=subprocess.check_output([str(binary),name],text=True,timeout=5)
        (directory/(name+'.txt')).write_text(output)
    getter=directory/'getter';getter.mkdir()
    for name in ('feature','inc','gcode','module'):(getter/name).mkdir()
    for name in ('host_machine_state.cpp','host_machine_state.h'):shutil.copy2(SRC/'feature'/name,getter/'feature'/name)
    fixture=r'''
#pragma once
#include <cassert>
#include <cstdint>
extern int critical;
#define ENABLED(V) V
#define DISABLED(V) (!V)
#define LLM_MACHINE_STATE 1
#define LLM_PROMPT_PROTOCOL 1
#define NUM_AXES 3
#define HOTENDS 1
#define EXTRUDERS 1
#define HAS_HEATED_BED 1
#define HAS_FAN 1
#define HAS_RESUME_CONTINUE 1
#define TERN0(C,V) ((C)?(V):0)
#define TERN(C,A,B) ((C)?(A):(B))
#define CRITICAL_SECTION_START() assert(critical==0);++critical
#define CRITICAL_SECTION_END() --critical
using AxisEnum=uint8_t;
inline uint32_t millis(){assert(critical==1);return 1234;}
struct Marlin{bool wait_for_user=true,wait_for_heatup=true;bool isRunning(){assert(critical==1);return true;}};
extern Marlin marlin;
struct Motion{uint8_t axes_homed=5,axes_trusted=1,extruder=0;float position[4]={.25f,1.25f,2.25f,3.25f};float workspace_offset[3]={-2,-1,0},home_offset[3]={4,5,6};float feedrate_mm_s=12.5f;int16_t feedrate_percentage=100;};extern Motion motion;
struct Planner{bool leveling_active=true;int16_t flow_percentage[1]={95};uint8_t movesplanned(){assert(critical==1);return 7;}};extern Planner planner;
struct Stepper{bool axis_is_enabled(AxisEnum a){assert(critical==1);return (11&(1<<a))!=0;}};extern Stepper stepper;
struct Gcode{bool axis_is_relative(AxisEnum a){assert(critical==1);return a==3;}};extern Gcode gcode;
struct Parser{float linear_unit_factor=25.4f;};extern Parser parser;
struct Thermal{float degHotend(int){assert(critical==1);return 23.5f;}int degTargetHotend(int){assert(critical==1);return 0;}float degBed(){assert(critical==1);return 22.25f;}int degTargetBed(){assert(critical==1);return 0;}};extern Thermal thermalManager;
struct Fan{uint8_t speed=128;};extern Fan fans[1];
'''
    (getter/'fixture.h').write_text(fixture)
    for name in ['inc/MarlinConfig.h','MarlinCore.h','gcode/gcode.h','gcode/parser.h','module/motion.h','module/planner.h','module/stepper.h','module/temperature.h','module/fans.h']:
        (getter/name).write_text('#include "'+('../' if '/' in name else '')+'fixture.h"\n')
    (getter/'main.cpp').write_text(r'''
#include "feature/host_machine_state.cpp"
#include <iostream>
int critical=0;Marlin marlin;Motion motion;Planner planner;Stepper stepper;Gcode gcode;Parser parser;Thermal thermalManager;Fan fans[1];
int main(){
 const auto state=host_machine_state_snapshot();assert(critical==0);
 assert(state.uptime==1234&&state.flags==15&&state.homed==5&&state.trusted==1&&state.enabled==11&&state.blocks==7&&state.relative==8&&state.tool==0);
 for(int i=0;i<4;++i)assert(state.position[i]==float(i)+.25f);
 for(int i=0;i<3;++i){assert(state.workspace[i]==(HAS_WORKSPACE_OFFSET?float(i)-2:0));assert(state.home[i]==(HAS_HOME_OFFSET?float(i)+4:0));}
 const float expected[]={INCH_MODE_SUPPORT?25.4f:1,12.5f,100,95,128,23.5f,0,22.25f,0};
 for(int i=0;i<9;++i)assert(state.values[i]==expected[i]);
 motion.position[0]=42;assert(host_machine_state_snapshot().position[0]==42&&critical==0);
 std::cout<<"getter ok\n";
}
''')
    for inch in (0,1):
        for offsets in (0,1):
            binary=getter/f'getter-{inch}-{offsets}'
            subprocess.run([COMPILER,'-std=gnu++14','-Wall','-Wextra',f'-DINCH_MODE_SUPPORT={inch}',f'-DHAS_WORKSPACE_OFFSET={offsets}',f'-DHAS_HOME_OFFSET={offsets}',str(getter/'main.cpp'),'-o',str(binary)],check=True)
            subprocess.run([str(binary)],check=True,capture_output=True,timeout=5)
    result=dict(wire_scenarios=5,getter_variants=4,existing_prompt_scenarios=11,
                compiler=COMPILER,physical_access=False,firmware_flashed=False,
                sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [SRC/'feature/host_machine_state.cpp',SRC/'feature/host_machine_state.h',SRC/'feature/host_prompt_wire.cpp']})
    (directory/'proof.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

if __name__=='__main__':
    import argparse
    cli=argparse.ArgumentParser();cli.add_argument('--output',type=Path);args=cli.parse_args()
    if args.output:args.output.mkdir(parents=True,exist_ok=True);qualify(args.output)
    else:
        with tempfile.TemporaryDirectory(prefix='llm-state-native-') as temporary:qualify(temporary)
