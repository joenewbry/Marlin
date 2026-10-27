"""Exercise the actual HeaterWatch template with a synthetic clock, no IO.

Run with an optional source header path to demonstrate the original regressions.
This tests template arming/expiry only, not full thermal shutdown or hardware.
"""
from pathlib import Path
import re, shutil, subprocess, sys, tempfile

def extract(text):
    start=text.index('template <int INCREASE, int HYSTERESIS, millis_t PERIOD>')
    opening=text.index('{',start); depth=1;end=opening+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]+';'

if __name__=='__main__':
    header=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[2]/'Marlin/src/module/temperature.h'
    text=header.read_text()
    template=extract(text)
    # Use the actual integer temperature type, wrap-safe comparison and 32-bit tick.
    prefix=r'''
#include <cstdint>
#include <cassert>
#include <algorithm>
#include <iostream>
using celsius_t=int16_t;using millis_t=uint32_t;
static millis_t tick;
millis_t millis(){return tick;}
#define ELAPSED(A,B) (int32_t((A)-(B))>=0)
#define SEC_TO_MS(V) ((V)*1000UL)
#define _MIN(A,B) std::min((A),(B))
'''
    main=r'''
int main(){
 HeaterWatch<2,4,60> h{};
 tick=100;h.restart(20,200);assert(h.target==22&&h.next_ms==60100);
 assert(!h.elapsed(60099));assert(h.elapsed(60100));
 tick=uint32_t(0-60000);h.restart(20,200);
 assert(h.next_ms!=0);assert(!h.elapsed(0));assert(h.elapsed(1));
 tick=100;h.restart(195,200);assert(h.next_ms==60100&&h.target==196);
 h.restart(196,200);assert(h.next_ms==0);
 h.restart(20,0);assert(h.next_ms==0);
 tick=UINT32_MAX-1000;h.restart(20,200);assert(!h.elapsed(tick));
 assert(!h.elapsed(h.next_ms-1));assert(h.elapsed(h.next_ms));
 std::cout<<"6 template scenarios passed\n";
}
'''
    with tempfile.TemporaryDirectory(prefix='llm-watch-') as d:
        source=Path(d)/'watch.cpp';source.write_text(prefix+template+main)
        binary=Path(d)/'watch'
        subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-std=c++14',str(source),'-o',str(binary)],check=True,capture_output=True,text=True)
        subprocess.run([str(binary)],check=True,timeout=5)
    for watch,protection in [('hotend','THERMAL_PROTECTION_HYSTERESIS'),('bed','THERMAL_PROTECTION_BED_HYSTERESIS'),('chamber','THERMAL_PROTECTION_CHAMBER_HYSTERESIS')]:
        match=re.search(r'typedef struct HeaterWatch<([^\n]+)> '+watch+'_watch_t;',text)
        assert match and match[1].split(',')[1].strip()==protection,(watch,'must hand off at runaway threshold')
    print('3 actual watch typedef threshold checks passed')
