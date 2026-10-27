"""Native tests of actual HostUI/wire/emergency sources. No hardware access.

Run: python3 buildroot/tests/llm_prompt_native.py
Requires clang++ or g++; C++ physical dependencies are stubbed. It does not
qualify serial interrupts, real screen behavior, motion or heater operation.
"""
from pathlib import Path
import shutil, subprocess, tempfile, json
SRC=Path(__file__).resolve().parents[2]/'Marlin/src'

def build_native_harness(build):
    BUILD=Path(build)
    BUILD.mkdir(parents=True,exist_ok=True)
    for d in ('feature','inc','HAL/shared','gcode'):(BUILD/d).mkdir(parents=True,exist_ok=True)
    files=('host_actions.cpp','host_actions.h','host_prompt_identity.h','host_prompt_wire.h','host_prompt_wire.cpp','host_prompt_inbox.h','e_parser.h','e_parser.cpp','host_prompt_rx_router.h')
    for f in files:shutil.copyfile(SRC/'feature'/f,BUILD/'feature'/f)
    (BUILD/'inc/MarlinConfigPre.h').write_text(r'''
    #pragma once
    #include <cstdint>
    #include <string>
    #include <iostream>
    extern std::string serial_output;
    #define HOST_ACTION_COMMANDS 1
    #define HOST_PROMPT_SUPPORT 1
    #define LLM_PROMPT_PROTOCOL 1
    #define EMERGENCY_PARSER 1
    #define HAS_GCODE_M876 1
    #define DISABLED(V) (!V)
    #define ADVANCED_PAUSE_FEATURE 1
    #define HAS_FILAMENT_SENSOR 1
    #define HAS_RESUME_CONTINUE 1
    #define M600_PURGE_MORE_RESUMABLE 1
    #define HAS_MEDIA 1
    #define GCODE_CASE_INSENSITIVE 0
    #define ENABLED(V) V
    #define BOTH(A,B) ((A)&&(B))
    #define ALL(A,B) BOTH(A,B)
    #define TERN_(C,V) V
    #define TERN0(C,V) ((C)?(V):0)
    #define WITHIN(V,A,B) ((V)>=(A)&&(V)<=(B))
    #define ISEOL(C) ((C)=='\n'||(C)=='\r')
    #define FORCE_INLINE inline
    #define PGMSTR(N,S) const char N[] = S
    using PGM_P=const char*;
    class __FlashStringHelper;
    using FSTR_P=const __FlashStringHelper*;
    #define F(S) reinterpret_cast<FSTR_P>(S)
    #define FPSTR(S) F(S)
    #define FTOP(S) reinterpret_cast<const char*>(S)
    inline void append(const char*s){serial_output+=s;}
    inline void append(FSTR_P s){append(FTOP(s));}
    template<class T,class...Rest> void append(T s,Rest... rest){append(s);append(rest...);}
    #define PORT_REDIRECT(X) do {} while(0)
    #define SERIAL_ECHOPGM(...) append(__VA_ARGS__)
    #define SERIAL_ECHOPGM_P(X) append(X)
    #define SERIAL_ECHO(X) append(X)
    #define SERIAL_ECHOLN(X) do{append(X);serial_output+='\n';}while(0)
    #define SERIAL_ECHOLNPGM_P(X) SERIAL_ECHOLN(X)
    #define SERIAL_CHAR(X) do{serial_output+=char(X);}while(0)
    #define SERIAL_EOL() do{serial_output+='\n';}while(0)
    #define CRITICAL_SECTION_START() do{}while(0)
    #define CRITICAL_SECTION_END() do{}while(0)
    ''')
    (BUILD/'inc/MarlinConfig.h').write_text('#include "MarlinConfigPre.h"\n')
    (BUILD/'HAL/shared/Marduino.h').write_text('#include "../../inc/MarlinConfigPre.h"\n')
    (BUILD/'MarlinCore.h').write_text('#pragma once\nstruct Marlin{bool wait_for_user=true; void user_resume(){wait_for_user=false;} void end_waiting(){wait_for_user=false;} void kill(const __FlashStringHelper*,void*,bool){}}; extern Marlin marlin;extern const char M112_KILL_STR[];\n')
    (BUILD/'feature/pause.h').write_text('#include "../MarlinCore.h"\nenum{PAUSE_RESPONSE_EXTRUDE_MORE=1,PAUSE_RESPONSE_RESUME_PRINT=2};extern int pause_menu_response;\n')
    (BUILD/'feature/runout.h').write_text('struct Runout{bool filament_ran_out=false,enabled=true;};extern Runout runout;\n')
    (BUILD/'gcode/queue.h').write_text('struct Queue{int calls=0;void inject_P(const char*){++calls;}};extern Queue queue;\n')
    (BUILD/'gcode/host').mkdir(exist_ok=True)
    (BUILD/'gcode/control').mkdir(exist_ok=True)
    shutil.copyfile(SRC/'gcode/host/M876.cpp',BUILD/'gcode/host/M876.cpp')
    shutil.copyfile(SRC/'gcode/control/M108_M112_M410.cpp',BUILD/'gcode/control/M108_M112_M410.cpp')
    (BUILD/'module').mkdir(exist_ok=True)
    (BUILD/'module/motion.h').write_text('struct Motion{void quickstop_stepper(){}};extern Motion motion;\n')
    (BUILD/'gcode/gcode.h').write_text('#pragma once\nstruct GcodeSuite{static void M108();static void M112();static void M410();static void M876();};\n')
    (BUILD/'main.cpp').write_text(r'''
    #include <cassert>
    #include "feature/host_actions.cpp"
    #include "feature/host_prompt_wire.cpp"
    #include "feature/e_parser.cpp"
    #include "feature/host_prompt_rx_router.h"
    #include "gcode/host/M876.cpp"
    #include "gcode/control/M108_M112_M410.cpp"
    std::string serial_output;
    extern const char M112_KILL_STR[]="Killed"; Motion motion;
    Marlin marlin; Runout runout;Queue queue;int pause_menu_response=0;
    extern const char M24_STR[]="M24";
    void feed(const std::string&s){auto state=EmergencyParser::EP_RESET;for(auto c:s)EmergencyParser::update(state,c);}
    int main(int argc,char**argv){
     assert(argc==2);std::string s=argv[1];HostPromptSession a{123,456};
     hostui.continue_prompt(F("Continue?"));auto first=host_prompt_identity.generation();
     if(s=="runtime"||s=="runtime_runout"){
      runout.filament_ran_out=s=="runtime_runout";
      serial_output.clear();char c;
      while(std::cin.get(c)){if(c=='~'){host_prompt_wire_process();host_response_process();std::cout<<serial_output;serial_output.clear();std::cout<<"STATE "<<marlin.wait_for_user<<" "<<host_prompt_protocol_busy<<"\n"<<std::flush;}else host_prompt_receive_byte(c);}return 0;
     }
     if(s=="deferred"){feed("M876 S0\n");assert(marlin.wait_for_user);host_response_process();assert(!marlin.wait_for_user);marlin.wait_for_user=true;host_response_process();assert(marlin.wait_for_user);}
     else if(s=="invalid_legacy"){
      for(auto line:{"M876 S00\n","M876 S+0\n","M876 S0junk\n","M876 S-0\n","M1080\n","M108junk\n"}){feed(line);host_response_process();assert(marlin.wait_for_user);}
      feed("M108 ;comment\n");assert(!marlin.wait_for_user);
     }
     else if(s=="router"){
      HostPromptRxRouter r;std::string out;
      const std::string input="M876 V1 I Q00000001\nM876 V10 invalid\nG1 X1\nM876 S0\n";
      for(auto c:input)r.receive(c,[&](uint8_t b){out+=char(b);});
      assert(out=="M876 V10 invalid\nG1 X1\nM876 S0\n");
     }
     else if(s=="dispatch_unbound"){GcodeSuite::M108();assert(!marlin.wait_for_user);}
     else if(s=="stale_legacy"){feed("M876 S0\n");hostui.continue_prompt(F("Replacement"));host_response_process();assert(marlin.wait_for_user);}
     else{
      assert(host_prompt_identity.bind(a));
      if(s=="bound_legacy"){host_prompt_token_mode=true;feed("M876 S0\nM108\n");host_response_process();GcodeSuite::M108();GcodeSuite::M876();assert(marlin.wait_for_user);}
      else if(s=="stale"){hostui.continue_prompt(F("New"));assert(host_token_response(a,first,0)==HostPromptCheck::StalePrompt);assert(marlin.wait_for_user);host_prompt_end_if_current(first);assert(host_prompt_identity.active());}
      else if(s=="runout"){runout.filament_ran_out=true;assert(host_token_response(a,first,0)==HostPromptCheck::PhysicalActionRequired);assert(marlin.wait_for_user&&runout.enabled);hostui.filament_load_prompt();assert(host_prompt_identity.buttons()==1);assert(!hostui.handle_response(1));assert(runout.enabled&&runout.filament_ran_out);}
      else if(s=="reason_map"){
       const PromptReason reasons[]={PROMPT_NOT_DEFINED,PROMPT_FILAMENT_RUNOUT,PROMPT_USER_CONTINUE,PROMPT_PAUSE_RESUME,PROMPT_INFO};
       for(uint8_t i=0;i<5;++i){HostUI::host_prompt_reason=reasons[i];assert(host_prompt_wire_reason()==i);}
       hostui.prompt_do(PROMPT_FILAMENT_RUNOUT_REHEAT,F("Reheat"),FPSTR(CONTINUE_STR));assert(host_prompt_wire_reason()==255);assert(host_token_response(a,host_prompt_identity.generation(),0)==HostPromptCheck::UnsupportedReason);assert(marlin.wait_for_user);
      }
      else if(s=="accept_once"){assert(host_token_response(a,first,0)==HostPromptCheck::Ready);assert(!marlin.wait_for_user);marlin.wait_for_user=true;assert(host_token_response(a,first,0)==HostPromptCheck::NoPrompt);assert(marlin.wait_for_user);}
      else if(s=="emergency"){host_prompt_token_mode=true;feed("M112\nM410\nM524\n");assert(EmergencyParser::killed_by_M112&&EmergencyParser::quickstop_by_M410&&EmergencyParser::sd_abort_by_M524);}
      else return 3;
     }
     std::cout<<"ok\n";
    }
    ''')
    compiler=shutil.which('clang++') or shutil.which('g++')
    result=subprocess.run([compiler,'-std=gnu++14','-Wall','-Wextra',str(BUILD/'main.cpp'),'-o',str(BUILD/'actions')],capture_output=True,text=True)
    if result.returncode:raise RuntimeError(result.stderr)
    return BUILD/'actions'

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='llm-v040-native-') as directory:
        binary=build_native_harness(directory)
        scenarios=('deferred','invalid_legacy','stale_legacy','bound_legacy','stale','runout','reason_map','accept_once','emergency','router','dispatch_unbound')
        for scenario in scenarios:
            subprocess.run([str(binary),scenario],check=True,capture_output=True,text=True,timeout=5)
        print(json.dumps({'passed':len(scenarios),'scenarios':scenarios}))
