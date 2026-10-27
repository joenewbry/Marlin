"""Actual watch/runaway/error/disable/loud-kill paths with recording IO stubs.

Run from any directory. Optional --source-root tests an earlier checkout.
This is not the full temperature task, ADC/interrupt/HAL or physical qualification.
"""
from pathlib import Path
import argparse,hashlib,json,re,shutil,subprocess,tempfile

def function(text, signature):
    start=text.index(signature);opening=text.index('{',start);depth=1;end=opening+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]

def build(root, directory):
    source=(root/'Marlin/src/module/temperature.cpp').read_text()
    header=(root/'Marlin/src/module/temperature.h').read_text()
    config=(root/'Marlin/Configuration_adv.h').read_text()
    names=('THERMAL_PROTECTION_PERIOD','THERMAL_PROTECTION_HYSTERESIS',
           'THERMAL_PROTECTION_BED_PERIOD','THERMAL_PROTECTION_BED_HYSTERESIS',
           'WATCH_TEMP_PERIOD','WATCH_TEMP_INCREASE','WATCH_BED_TEMP_PERIOD','WATCH_BED_TEMP_INCREASE')
    settings={n:int(re.search(r'^\s*#define '+n+r'\s+(\d+)',config,re.M)[1]) for n in names}
    snippets={n:function(source,signature) for n,signature in {
        'runaway':'void Temperature::tr_state_machine_t::run(',
        'error':'void Temperature::_temp_error(',
        'disable':'void Temperature::disable_all_heaters()',
        'loud_kill':'inline void loud_kill(',
        'hotend_watch':'if (watch_hotend[e].elapsed(ms))',
        'bed_watch':'if (watch_bed.elapsed(ms))'}.items()}
    snippets['watch_template']=function(header,'template <int INCREASE, int HYSTERESIS, millis_t PERIOD>')+';'
    for n,signature in [('start_hotend','static void start_watching_hotend('),('start_bed','static void start_watching_bed()')]:snippets[n]=function(header,signature)
    a=header.index('      enum TRState');b=header.index('      static tr_state_machine_t tr_state_machine',a)
    snippets['declarations']=header[a:b]
    snippets['typedefs']='\n'.join(re.search(r'typedef struct HeaterWatch<[^\n]+> '+n+'_watch_t;',header)[0] for n in ('hotend','bed'))
    pre=r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>
#define ENABLED(V) V
#define CHOOSE_1(A,B) A
#define CHOOSE_0(A,B) B
#define PICK_(C) CHOOSE_##C
#define PICK(C) PICK_(C)
#define TERN(C,A,B) PICK(C)(A,B)
#define TERN_(C,...) TERN(C,__VA_ARGS__,)
#define TERN0(C,...) TERN(C,__VA_ARGS__,false)
#define TERN1(C,...) TERN(C,__VA_ARGS__,true)
#define ARG_0(...)
#define ARG_1(...) , __VA_ARGS__
#define ARG_(C) ARG_##C
#define ARG(C) ARG_(C)
#define OPTARG(C,...) ARG(C)(__VA_ARGS__)
#define OPTCODE(C,...) TERN_(C,__VA_ARGS__;)
#define UNUSED(X) (void)(X)
#define _MIN(A,B) std::min((A),(B))
#define SEC_TO_MS(V) ((V)*1000UL)
#define PENDING(A,B) (int32_t((A)-(B))<0)
#define ELAPSED(A,B) (!PENDING(A,B))
#define GET_TEXT_F(X) #X
#define F(X) X
#define FPSTR(X) X
#define C(X) X
#define LOW 0
#define HOTENDS 1
#define HOTEND_LOOP() for(uint8_t e=0;e<HOTENDS;++e)
#define REPEAT(N,F) F(0)
#define WRITE_HEATER_0(V) nozzle_pin=(V)
#define WRITE_HEATER_BED(V) bed_pin=(V)
#define SERIAL_ERROR_START() serial_error=true
#define SERIAL_ECHO(...) serial_append(__VA_ARGS__)
#define SERIAL_ECHOPGM(...)
#define SERIAL_EOL()
#define HAS_HOTEND 1
#define HAS_TEMP_HOTEND 1
#define HAS_HEATED_BED 1
#define HAS_TEMP_BED 1
#define WATCH_HOTENDS 1
#define WATCH_BED 1
#define HAS_HEATED_CHAMBER 0
#define HAS_COOLER 0
#define HAS_TEMP_REDUNDANT 0
#define HAS_TEMP_COOLER 0
#define HAS_TEMP_PROBE 0
#define HAS_TEMP_BOARD 0
#define HAS_TEMP_SOC 0
#define HAS_TEMP_CHAMBER 0
#define HEATER_IDLE_HANDLER 1
#define THERMAL_PROTECTION_VARIANCE_MONITOR 0
#define ADAPTIVE_FAN_SLOWING 0
#define AUTOTEMP 1
#define PROBING_HEATERS_OFF 0
#define BOGUS_TEMPERATURE_GRACE_PERIOD 0
#define HAS_BOGUS_TEMPERATURE_GRACE_PERIOD 0
#define ERR_INCLUDE_TEMP 0
#define HAS_BEEPER 1
#define NOZZLE_PARK_FEATURE 1
#define SOVOL_SV06_RTS 0
#define E3S1PRO_RTS 1
#define DWIN_CREALITY_LCD 0
#define EXTENSIBLE_UI 0
#define E_NAME e
#define HOTEND_INDEX e
#define STR_E0 "E0"
#define STR_E1 "E1"
#define STR_E2 "E2"
#define STR_E3 "E3"
#define STR_E4 "E4"
#define STR_E5 "E5"
#define STR_E6 "E6"
#define STR_E7 "E7"
using millis_t=uint32_t;using celsius_t=int16_t;using celsius_float_t=float;
using heater_id_t=int8_t;using FSTR_P=const char*;using IdleIndex=int;
constexpr heater_id_t H_BED=-1;constexpr int MF_KILLED=1;
uint32_t tick=0;millis_t millis(){return tick;}
int nozzle_pin=1,bed_pin=1,kills=0,watchdogs=0,screens=0,parks=0,syncs=0;
bool serial_error=false,running=true,homing_needed=true;
std::string serial_message,kill_message;
void serial_append(){}
void serial_append(const char*s){serial_message+=s;}
void serial_append(char c){serial_message+=c;}
void serial_append(int n){serial_message+=std::to_string(n);}
template<typename T>void serial_append(T t){serial_message+=std::to_string(t);}
template<typename T,typename U,typename...R>void serial_append(T t,U u,R...r){serial_append(t);serial_append(u,r...);}
struct Heater{celsius_t target;int soft_pwm_amount;};
Heater temp_hotend[1]={{200,100}},temp_bed={60,100};
struct Autotemp{bool enabled=true;}autotemp;
struct Idle{bool timed_out=false;}heater_idle[2];
IdleIndex idle_index_for_id(heater_id_t h){return h==H_BED?1:0;}
void setTargetHotend(int t,int e){temp_hotend[e].target=t;}
void setTargetBed(int t){temp_bed.target=t;}
void assert_off(){assert(!temp_hotend[0].target&&!temp_bed.target&&!temp_hotend[0].soft_pwm_amount&&!temp_bed.soft_pwm_amount&&!nozzle_pin&&!bed_pin&&!autotemp.enabled);}
struct Marlin{bool isRunning(){return running;}void setState(int){running=false;}void kill(FSTR_P msg,FSTR_P){assert_off();++kills;kill_message=msg;}}marlin;
struct HAL{void watchdog_refresh(){++watchdogs;}}hal;
struct Buzzer{void click(int){}void on(){}}buzzer;
void delay(int){}
struct Motion{bool homing_needed_error(){return homing_needed;}}motion;
struct Nozzle{void park(int){assert_off();++parks;}}nozzle;
struct Planner{void synchronize(){assert_off();++syncs;}}planner;
void RTS_ShowPage(int page){assert(page==31);++screens;}
float actual=20;
float degHotend(int){return actual;}float degBed(){return actual;}
int degTargetHotend(int){return temp_hotend[0].target;}int degTargetBed(){return temp_bed.target;}
const char*str_t_thermal_runaway="THERMAL RUNAWAY";
const char*str_t_heating_failed="HEATING FAILED";
#define _TEMP_ERROR(E,M,L,D) _temp_error(heater_id_t(E),M,GET_TEXT_F(L))
'''
    globals_code=snippets['watch_template']+'\n'+snippets['typedefs']+'\nhotend_watch_t watch_hotend[1]{};bed_watch_t watch_bed{};\n'
    cls='struct Temperature{\nstatic void _temp_error(heater_id_t,FSTR_P,FSTR_P);\nstatic void disable_all_heaters();\n'+snippets['declarations']+snippets['start_hotend']+snippets['start_bed']+'''
static void check_watch(bool bed){const millis_t ms=millis();int e=0;
if(bed){'''+snippets['bed_watch']+'}else{'+snippets['hotend_watch']+'}}\n};\nTemperature thermalManager;\n'
    main=r'''
int main(int argc,char**argv){
 if(argc!=3)return 2;std::string s=argv[1];bool bed=std::string(argv[2])=="bed";
 const int target=bed?60:200,hyst=bed?THERMAL_PROTECTION_BED_HYSTERESIS:THERMAL_PROTECTION_HYSTERESIS;
 const int period=bed?THERMAL_PROTECTION_BED_PERIOD:THERMAL_PROTECTION_PERIOD;
 const int watch_period=bed?WATCH_BED_TEMP_PERIOD:WATCH_TEMP_PERIOD;
 const int increase=bed?WATCH_BED_TEMP_INCREASE:WATCH_TEMP_INCREASE;
 Temperature::tr_state_machine_t state{};
 auto restart=[&](){if(bed)Temperature::start_watching_bed();else Temperature::start_watching_hotend(0);};
 auto deadline=[&](){return bed?watch_bed.next_ms:watch_hotend[0].next_ms;};
 auto run=[&](){state.run(actual,bed?temp_bed.target:temp_hotend[0].target,bed?H_BED:0,period,hyst);};
 bool fault=false;int before_state=-1;bool before_watch=true;
 if(s=="direct_runaway"||s=="repeat_fault"||s=="unhomed"||s=="homed"||s=="wrap_runaway"){
  homing_needed=s!="homed";tick=s=="wrap_runaway"?UINT32_MAX-1000:1000;actual=target;run();
  uint32_t due=tick+period*1000;tick=due-1;actual=target-hyst-1;run();assert(!kills);
  tick=due;run();fault=true;
  if(s=="repeat_fault"){run();assert(kills==1);}
 }else if(s=="idle_timeout"){
  actual=target;run();heater_idle[bed?1:0].timed_out=true;tick=period*2000;actual=20;run();assert(state.state==Temperature::TRInactive);
 }else if(s=="watch_no_rise"||s=="watch_wrap"||s=="watch_zero"||s=="watch_enough"||s=="watch_off"){
  tick=s=="watch_wrap"?UINT32_MAX-1000:s=="watch_zero"?uint32_t(0-watch_period*1000):1000;
  restart();auto due=deadline();assert(due);
  tick=due-1;Temperature::check_watch(bed);assert(!kills);
  if(s=="watch_enough")actual+=increase;
  if(s=="watch_off"){if(bed)temp_bed.target=0;else temp_hotend[0].target=0;restart();}
  tick=due;Temperature::check_watch(bed);fault=s!="watch_enough"&&s!="watch_off";
 }else if(s=="boundary_drop"||s=="above_drop"||s=="boundary_hold"||s=="stall"||s=="normal"){
  restart();uint32_t drop_at=(watch_period+1)*1000;
  for(tick=0;tick<=600000&&!kills;tick+=1000){
   if(tick>=1000)actual=s=="normal"?target:s=="stall"?target-hyst-1:s=="above_drop"?target-hyst+1:target-hyst;
   if(tick==drop_at){before_state=state.state;before_watch=deadline()!=0;}
   if((s=="boundary_drop"||s=="above_drop")&&tick>=drop_at)actual=20;
   if(bed)Temperature::check_watch(true);if(kills)break;
   run();if(kills)break;
   if(!bed)Temperature::check_watch(false);
  }
  fault=s=="boundary_drop"||s=="above_drop"||s=="stall";
 }else return 3;
 std::cout<<"{\"scenario\":\""<<s<<"\",\"bed\":"<<bed<<",\"kills\":"<<kills
 <<",\"state\":"<<int(state.state)<<",\"before_state\":"<<before_state<<",\"before_watch\":"<<before_watch
 <<",\"now\":"<<tick<<",\"parks\":"<<parks<<",\"syncs\":"<<syncs<<",\"screens\":"<<screens
 <<",\"nozzle_target\":"<<temp_hotend[0].target<<",\"bed_target\":"<<temp_bed.target
 <<",\"nozzle_pwm\":"<<temp_hotend[0].soft_pwm_amount<<",\"bed_pwm\":"<<temp_bed.soft_pwm_amount
 <<",\"nozzle_pin\":"<<nozzle_pin<<",\"bed_pin\":"<<bed_pin<<",\"autotemp_enabled\":"<<autotemp.enabled
 <<",\"message\":\""<<serial_message<<"\",\"kill_message\":\""<<kill_message<<"\"}\n";
 if(fault){assert(kills==1);assert(serial_message.find(s.find("watch_")==0||s=="stall"?"HEATING FAILED":"THERMAL RUNAWAY")==0);assert_off();assert(serial_error);assert(screens>=1);assert(parks==(s=="homed"));assert(syncs==parks);}
 else{assert(!kills);if(s=="boundary_hold"||s=="normal"){assert(state.state==Temperature::TRStable);assert(!deadline());}}
 if(s=="boundary_drop"||s=="above_drop")assert(tick<=uint32_t(watch_period+period+2)*1000);
 if(s=="boundary_drop"||s=="above_drop"||s=="boundary_hold"){assert(before_state==Temperature::TRStable);assert(!before_watch);}
}
'''
    cpp=directory/'main.cpp'
    cpp.write_text(''.join(f'#define {k} {v}\n' for k,v in settings.items())+pre+globals_code+cls+snippets['loud_kill']+snippets['error']+snippets['disable']+snippets['runaway']+main)
    binary=directory/'thermal-paths'
    result=subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-std=c++17','-O0',str(cpp),'-o',str(binary)],capture_output=True,text=True)
    if result.returncode:raise RuntimeError(result.stderr)
    evidence={'settings':settings,'snippets_sha256':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in snippets.items()},'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'header_sha256':hashlib.sha256(header.encode()).hexdigest(),'configuration_sha256':hashlib.sha256(config.encode()).hexdigest(),'physical_qualified':False,'full_manager_qualified':False,'recording_stubs':['HAL pins','target setters','serial','buzzer/delay','screen','marlin state/kill','nozzle park','planner sync','clock','sensor samples','idle state'],'feature_branches':{'single_hotend':True,'heated_bed':True,'idle_handler':True,'autotemp':True,'beeper':True,'nozzle_park':True,'e3s1pro_rts':True,'variance_monitor':False,'grace_period':False}}
    return binary,evidence

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();results=[];failures=[]
    scenarios=('direct_runaway','repeat_fault','unhomed','homed','wrap_runaway','idle_timeout',
               'watch_no_rise','watch_wrap','watch_zero','watch_enough','watch_off',
               'boundary_drop','above_drop','boundary_hold','stall','normal')
    with tempfile.TemporaryDirectory(prefix='llm-thermal-paths-') as d:
        binary,evidence=build(args.source_root,Path(d))
        for heater in ('hotend','bed'):
            for scenario in scenarios:
                r=subprocess.run([str(binary),scenario,heater],capture_output=True,text=True,timeout=5)
                if r.returncode:failures.append({'scenario':scenario,'heater':heater,'returncode':r.returncode,'stderr':r.stderr})
                else:results.append(json.loads(r.stdout))
    report={'passed':len(results),'failed':len(failures),'results':results,'failures':failures,'evidence':evidence}
    if args.output:args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':len(results),'failed':len(failures),'failures':failures}))
    raise SystemExit(bool(failures))
