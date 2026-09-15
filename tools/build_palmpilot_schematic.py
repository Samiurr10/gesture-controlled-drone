"""Generate the PalmPilot module-level schematic and assembly package.

Vector drawings and connection schedules are the authored design, not an ERC-
checked PCB schematic. Source evidence lives in docs/schematic-research-*.md.
"""
from pathlib import Path
import argparse, math, json, textwrap, html, os

ROOT = Path(__file__).resolve().parents[1]

def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--output-dir', type=Path, default=ROOT / 'output/pdf',
        help='directory for generated PDF, SVG sheets, wirelists and manifest (default: repository output/pdf)',
    )
    return parser.parse_args()

# Resolve --help before loading optional PDF dependencies or writing any files.
ARGS = parse_args() if __name__ == '__main__' else None

import reportlab
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

OUT = ROOT / 'output/pdf'
SVG = OUT / 'schematic-sheets'
ASSETS = ROOT / 'hardware/schematics/sources'
W,H = 842,595
INK='#163046'; MUTED='#506273'; BLUE='#176BA0'; RED='#C33736'
ORANGE='#BD700B'; GREEN='#087C68'; GND='#384551'; LIGHT='#E9EFF3'
PURPLE='#7749A4'; WHITE='#FFFFFF'; PALE='#F6F8FA'
PDF=OUT/'PalmPilot_Full_Schematic_and_Build_Guide.pdf'

def register_fonts():
    """Use installed Arial where available, otherwise ReportLab's bundled Vera."""
    candidates = [
        (Path('/System/Library/Fonts/Supplemental/Arial.ttf'),
         Path('/System/Library/Fonts/Supplemental/Arial Bold.ttf')),
        (Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/arial.ttf',
         Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/arialbd.ttf'),
        (Path(reportlab.__file__).parent / 'fonts/Vera.ttf',
         Path(reportlab.__file__).parent / 'fonts/VeraBd.ttf'),
    ]
    for regular, bold in candidates:
        if regular.is_file() and bold.is_file():
            pdfmetrics.registerFont(TTFont('ArialRegular', str(regular)))
            pdfmetrics.registerFont(TTFont('ArialBold', str(bold)))
            return
    raise RuntimeError('No usable font pair found. Reinstall ReportLab with its bundled Vera fonts.')

class Book:
    def __init__(self):
        self.c=canvas.Canvas(str(PDF), pagesize=(W,H))
        self.c.setTitle('PalmPilot / Manta Flow - Full Wiring Schematic and Build Guide - Rev A')
        self.c.setAuthor('Prepared with Codex from the project BOM and manufacturer documentation')
        self.page=0; self.svg=[]; self.pages=[]; self.textlog=[]
    def line(self,x1,y1,x2,y2,color=INK,width=1,dash=None):
        c=self.c;c.setStrokeColor(HexColor(color));c.setLineWidth(width)
        c.setDash(dash or []);c.line(x1,H-y1,x2,H-y2);c.setDash([])
        self.svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"'+(f' stroke-dasharray="{dash[0]} {dash[1]}"' if dash else '')+'/>')
    def rect(self,x,y,w,h,fill=WHITE,stroke=LIGHT,width=1):
        self.c.setFillColor(HexColor(fill));self.c.setStrokeColor(HexColor(stroke));self.c.setLineWidth(width)
        self.c.rect(x,H-y-h,w,h,fill=1,stroke=1)
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>')
    def circle(self,x,y,r,fill=WHITE,stroke=INK,width=1):
        self.c.setFillColor(HexColor(fill));self.c.setStrokeColor(HexColor(stroke));self.c.setLineWidth(width)
        self.c.circle(x,H-y,r,stroke=1,fill=1)
        self.svg.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>')
    def text(self,x,y,s,size=10,color=INK,bold=False,align='left'):
        s=str(s);font='ArialBold' if bold else 'ArialRegular'
        self.c.setFillColor(HexColor(color));self.c.setFont(font,size)
        if align=='center': self.c.drawCentredString(x,H-y,s)
        elif align=='right': self.c.drawRightString(x,H-y,s)
        else:self.c.drawString(x,H-y,s)
        anchor={'left':'start','center':'middle','right':'end'}[align]
        self.svg.append(f'<text x="{x}" y="{y}" font-family="Arial,Helvetica,sans-serif" font-size="{size}" fill="{color}" font-weight="{700 if bold else 400}" text-anchor="{anchor}">{html.escape(s)}</text>')
        self.textlog.append(s)
    def wrap(self,s,width,size=10,bold=False):
        font='ArialBold' if bold else 'ArialRegular';lines=[]
        for para in str(s).split('\n'):
            line=''
            for word in para.split():
                if stringWidth(word,font,size)>width:
                    # Long source URLs are only used in a separate linked list.
                    chunks=textwrap.wrap(word,max(10,int(width/(size*.55))),break_long_words=True)
                else:chunks=[word]
                for part in chunks:
                    candidate=(line+' '+part).strip()
                    if line and stringWidth(candidate,font,size)>width:lines.append(line);line=part
                    else:line=candidate
            lines.append(line)
        return lines
    def para(self,x,y,s,width,size=10,color=INK,bold=False,leading=None):
        leading=leading or size*1.35
        lines=self.wrap(s,width,size,bold)
        for i,t in enumerate(lines):self.text(x,y+i*leading,t,size,color,bold)
        assert y+(len(lines)-1)*leading < 554, (self.page,s[:50],y,len(lines))
        return y+len(lines)*leading
    def box(self,x,y,w,h,title,body='',color=BLUE):
        self.rect(x,y,w,h,PALE,LIGHT)
        self.rect(x,y,4,h,color,color)
        self.text(x+13,y+20,title,11,color,True)
        if body:self.para(x+13,y+38,body,w-26,9.5)
    def ground(self,x,y,net=''):
        self.line(x,y,x,y+7,GND)
        for dy,ww in [(7,12),(11,8),(15,4)]:self.line(x-ww/2,y+dy,x+ww/2,y+dy,GND)
        if net:self.text(x+10,y+13,net,8,GND)
    def dot(self,x,y,color=INK):self.circle(x,y,2,color,color)
    def resistor(self,x1,y,x2,label,color=INK):
        mid=(x1+x2)/2
        self.line(x1,y,mid-16,y,color);self.rect(mid-16,y-5,32,10,WHITE,color)
        self.line(mid+16,y,x2,y,color);self.text(mid,y-10,label,8.5,color,align='center')
    def rv(self,x,y1,y2,label):
        mid=(y1+y2)/2;self.line(x,y1,x,mid-13);self.rect(x-5,mid-13,10,26,WHITE,INK);self.line(x,mid+13,x,y2)
        self.text(x+10,mid+3,label,8.5)
    def capv(self,x,y1,y2,label):
        mid=(y1+y2)/2;self.line(x,y1,x,mid-3);self.line(x-8,mid-3,x+8,mid-3)
        self.line(x-8,mid+3,x+8,mid+3);self.line(x,mid+3,x,y2);self.text(x+11,mid+3,label,8.5)
    def arrow(self,x1,y1,x2,y2,color=BLUE,width=1.3,dash=None):
        self.line(x1,y1,x2,y2,color,width,dash)
        a=math.atan2(y2-y1,x2-x1)
        for d in [-.5,.5]:self.line(x2,y2,x2-7*math.cos(a+d),y2-7*math.sin(a+d),color,width)
    def table(self,x,y,widths,headers,rows,size=9.2,leading=11.6,pad=7):
        yy=y
        for ri,row in enumerate([headers]+rows):
            wrapped=[self.wrap(v,w-2*pad,size,ri==0) for v,w in zip(row,widths)]
            rh=max(len(v) for v in wrapped)*leading+pad*2
            assert yy+rh<=546, (self.page,'table overflow',yy+rh,row)
            xx=x
            for w,lines in zip(widths,wrapped):
                self.rect(xx,yy,w,rh,INK if ri==0 else (WHITE if ri%2==0 else PALE),LIGHT,.6)
                for li,s in enumerate(lines):self.text(xx+pad,yy+pad+size+li*leading,s,size,WHITE if ri==0 else INK,ri==0)
                xx+=w
            yy+=rh
        return yy
    def new(self,title,subtitle='',sheet=None):
        if self.page:self.end()
        self.page+=1;self.svg=[];self.textlog=[];self.sheet=sheet
        self.c.bookmarkPage(f'page{self.page}')
        self.c.addOutlineEntry(title,f'page{self.page}',level=0,closed=False)
        self.rect(0,0,W,H,WHITE,WHITE)
        self.text(30,25,'PALMPILOT / MANTA FLOW',9,BLUE,True)
        self.text(812,25,'REV A  |  14 SEP 2026  |  DEVELOPMENT SCHEMATIC',8,MUTED,align='right')
        self.text(30,51,title,21,INK,True)
        if subtitle:self.text(30,70,subtitle,9.5,MUTED)
        self.line(30,80,812,80,LIGHT)
    def footer(self,source):
        self.text(30,553,source,7.5,MUTED)
    def image(self,path,x,y,w,h):
        self.c.drawImage(str(path),x,H-y-h,width=w,height=h,preserveAspectRatio=True,anchor='c',mask='auto')
    def end(self):
        self.line(30,564,812,564,LIGHT)
        self.text(30,581,'Module-level interconnect drawing. Confirm received revisions and test with propellers removed.',8,MUTED)
        self.text(812,581,f'{self.page:02d}',10,BLUE,True,align='right')
        if self.sheet:
            (SVG/(self.sheet+'.svg')).write_text('<svg xmlns="http://www.w3.org/2000/svg" width="842" height="595" viewBox="0 0 842 595">'+''.join(self.svg)+'</svg>')
        self.pages.append({'page':self.page,'title':self.textlog[2] if len(self.textlog)>2 else '', 'text':self.textlog[:]})
        self.c.showPage()
    def save(self):self.end();self.c.save()

WIRES=[]
def wire(id,net,src,dst,gauge,notes='',status='specified'):
    WIRES.append(dict(id=id,net=net,source=src,destination=dst,wire=gauge,notes=notes,status=status))

# Power and ESC harness: physical pin numbering is introduced on the connector sheet.
for row in [
('P01','VBAT','BT1 mating XT60 +','U2 VBAT large + pad','12 AWG red','One 4S pack; connector + mark controls polarity'),
('P02','AIR_GND','BT1 mating XT60 -','U2 GND large - pad','12 AWG black','Short return paired with P01'),
('P03','VBAT','C1 +','U2 VBAT large + pad','Capacitor lead','1000 uF / 35 V; short and insulated'),
('P04','AIR_GND','C1 - striped side','U2 GND large - pad','Capacitor lead','Secure capacitor body'),
]:wire(*row)
for i,(net,src,dst,notes) in enumerate([
('VBAT','VBAT','B+','RAW battery supply to FC, not 5 V'),
('ESC_TLM','TLM','R7','ESC UART telemetry; no TX7 connection'),
('AIR_GND','GND','GND','Common signal ground'),
('ESC_CURRENT','CURRENT','CURRENT','Analog current signal, not power'),
('MOTOR1','M1','M1','FC output -> ESC channel 1'),
('MOTOR2','M2','M2','FC output -> ESC channel 2'),
('MOTOR3','M3','M3','FC output -> ESC channel 3'),
('MOTOR4','M4','M4','FC output -> ESC channel 4')],1):
    wire(f'E{i:02}',net,f'U2 harness {src}',f'U1 ESC1 {dst}','Supplied 8-pin harness',notes)

PERIPHERALS=[
('A01','AIR_5V','U1 5V','U3 RP1 5V','26 AWG red','Receiver power'),
('A02','AIR_GND','U1 G','U3 RP1 GND','26 AWG black','Receiver reference'),
('A03','CRSF_UP','U3 RP1 TX','U1 R3','28 AWG white','Receiver commands -> FC'),
('A04','CRSF_DOWN','U1 T3','U3 RP1 RX','28 AWG blue','FC telemetry -> receiver'),
('A05','AIR_5V','U1 5V','U4 Matek 5V','26 AWG red','4-9 V allowed; use regulated 5 V'),
('A06','AIR_GND','U1 G','U4 Matek G','26 AWG black','GNSS and compass ground'),
('A07','GPS_UP','U4 Matek TX','U1 R4','Supplied blue','GNSS data -> FC; verify supplied color'),
('A08','GPS_DOWN','U1 T4','U4 Matek RX','Supplied yellow','FC configuration -> GNSS; verify supplied color'),
('A09','I2C_SCL','U1 SCL','U4 Matek CL','28 AWG green','Compass clock; do not add 5 V pull-ups'),
('A10','I2C_SDA','U1 SDA','U4 Matek DA','Supplied white','Compass data; 3.3 V logic; verify color'),
('A11','AIR_5V','U1 5V','U5 4-pin contact 1 VCC','26 AWG red','Standalone module power'),
('A12','AIR_GND','U1 G','U5 4-pin contact 4 GND','26 AWG black','Contacts 2/3 NC; leave 3-pin connector empty'),
('A13','AIR_5V','U1 5V','BZ1 Finder 2 5V','26 AWG red','Buzzer supply/charging'),
('A14','AIR_GND','U1 G','BZ1 Finder 2 GND','26 AWG black','Must connect real GND'),
('A15','BUZZ_LOW','U1 Z-','BZ1 Finder 2 BZ','28 AWG yellow','Switched negative trigger, not GND'),
]
for row in PERIPHERALS:wire(*row)
for row in [
('RF1','ELRS_RF','U3 RP1 U.FL','Supplied 2.4 GHz T antenna','Factory coax','Push straight down; strain-relieve coax'),
('RF2','RID_BT','U5 left U.FL (marked BT)','Short black Bluetooth antenna','Factory coax','Board view: RF sockets top, wire sockets bottom'),
('RF3','RID_GNSS','U5 right U.FL (marked GNSS)','Long grey GNSS antenna','Factory coax','Do not interchange with BT antenna'),
]:wire(*row)
for n,pos in [(1,'rear-right'),(2,'front-right'),(3,'rear-left'),(4,'front-left')]:
    for p,l in enumerate('UVW',1):wire(f'M{n}{l}',f'PHASE_{n}{l}',f'U2 motor bank {n} phase {p}',f'M{n} {pos} lead {l}','Match motor lead AWG',f'U/V/W are build labels; swap any two phases if direction is wrong')

# Sensing channels and local power. Separate power domains are never joined.
FINGERS=['thumb','index','middle','ring','little']
GPIO=['P0.04','P0.05','P0.30','P0.28','P0.02']
for hand,ref in [('L','U6'),('R','U7')]:
    for i,finger in enumerate(FINGERS,1):
        net=f'{hand}_A{i-1}';j=f'J{hand}{i}';r=f'R{hand}{i}';cap=f'C{hand}{i}'
        rows=[
          (f'{hand}{i}a',f'{hand}_3V',f'{ref} 3V',f'{j}.1 -> F{hand}{i} terminal 1','30 AWG red','Flex sensor is nonpolar'),
          (f'{hand}{i}b',net,f'F{hand}{i} terminal 2 -> {j}.2',f'{ref} A{i-1}','30 AWG signal',f'{finger}; node N{hand}{i}'),
          (f'{hand}{i}c',net,f'{ref} A{i-1}',f'{r}.1','Local trace/jumper','47 kohm, 1%, 0.125 W or higher'),
          (f'{hand}{i}d',f'{hand}_GND',f'{r}.2',f'{ref} GND','Local trace/jumper','Divider lower leg'),
          (f'{hand}{i}e',net,f'{ref} A{i-1}',f'{cap}.1','Local trace/jumper','100 nF, X7R, >=10 V'),
          (f'{hand}{i}f',f'{hand}_GND',f'{cap}.2',f'{ref} GND','Local trace/jumper','Place RC by ADC header'),
        ]
        for row in rows:wire(*row)
for letter,ref,bt in [('L','U6','BT2'),('R','U7','BT3'),('H','U8','BT4')]:
    wire(f'{letter}P1',f'{letter}_BAT',f'{bt} +',f'{ref} JST BAT +','Factory battery lead','Adafruit #1578, protected 1S 500 mAh')
    wire(f'{letter}P2',f'{letter}_GND',f'{bt} -',f'{ref} JST BAT -','Factory battery lead','Check connector polarity; never series-connect cells')
    wire(f'{letter}P3',f'{letter}_EN',f'{ref} EN',f'SW{letter} common','28 AWG signal','SPDT slide used as SPST')
    wire(f'{letter}P4',f'{letter}_GND',f'SW{letter} OFF throw',f'{ref} GND','28 AWG black','Other throw NC; closed EN-GND means OFF')
for sw,ref,pin,label,rail,pull,series,cap in [
    ('SW4','U6','D5','left enable','L','R201','R202','C201'),
    ('SW5','U8','D6','hub calibration','H','R203','R204','C202')]:
    net=label.replace(' ','_')
    for i,(a,b,n,note) in enumerate([
        (f'{ref} 3V',f'{pull}.1',rail+'_3V','10k external pull-up'),
        (f'{pull}.2',f'{ref} {pin}',net,'GPIO configured INPUT; active low'),
        (f'{ref} {pin}',f'{series}.1',net,'1k in series toward button'),
        (f'{series}.2',f'{sw} contact 1',sw+'_LEAD','Normally open pushbutton'),
        (f'{sw} contact 2',f'{ref} GND',rail+'_GND','Opposite contacts; not joined same-side legs'),
        (f'{ref} {pin}',f'{cap}.1',net,'100nF X7R >=10 V'),
        (f'{cap}.2',f'{ref} GND',rail+'_GND','Capacitor at MCU pin'),
    ],1):wire(f'{sw}.{i}',n,a,b,'28 AWG / local trace',note)

TRAINER=[
('H01','H_3V','U8 3V','U301 pin 5 VCC','Local wire','SN74LVC1G125DBVR; verify adapter map'),
('H02','H_GND','U8 GND','U301 pin 3 GND','Local wire','Logic supply reference'),
('H03','PPM_A','U8 D5 (P1.08)','U301 pin 2 A','Local wire','PPM waveform input'),
('H04','PPM_OEn','U8 D9 (P0.26)','U301 pin 1 /OE','Local wire','LOW enables buffer; HIGH disables'),
('H05','H_3V','U8 3V','R301.1','Local trace','10k pull-up'),
('H06','PPM_OEn','R301.2','U301 pin 1 /OE','Local trace','Holds output disabled in reset'),
('H07','PPM_A','U301 pin 2 A','R302.1','Local trace','100k input pull-down'),
('H08','H_GND','R302.2','U8 GND','Local trace','Defines idle input'),
('H09','H_3V','U301 pin 5 VCC','C301.1','Local trace','100nF, at IC'),
('H10','H_GND','C301.2','U301 pin 3 GND','Local trace','Decoupling return'),
('H11','PPM_Y','U301 pin 4 Y','R303.1','Local trace','1k series resistor'),
('H12','PPM_PRE','R303.2','JP301.1 / TP301','Local trace','Test here with jumper removed'),
('H13','PPM_CABLE','JP301.2 / TP302','J301 TS tip','Shielded signal','JP301 shunt OPEN until Pocket compatibility verified'),
('H14','H_GND','U8 GND','J301 TS sleeve','Shield / return','Only shared ground between hub and Pocket'),
]
for row in TRAINER:wire(*row,status='bench prototype; verify Pocket input before joining JP301')

# Source register: all sources are linked in the PDF and the editable README.
SOURCES=[
('S01','Project baseline - attached PalmPilot_BOM.pdf','local: docs/reference/PalmPilot_BOM.pdf','34 pages; aircraft pp1-2, hand kit pp5-6, electrical pp23-28.'),
('S02','Holybro Kakute H7 v1.5 stack and specifications','https://holybro.com/products/kakute-h7-v1-stacks','Exact 11091+31102 stack; current v1.5 specification.'),
('S03','Holybro Kakute H7 pinout','https://docs.holybro.com/autopilot/kakute-h7-v1-v2-mini/kakute-h7-v1/pinout','Pad names; ESC and VTX port functions. Older rail figures noted.'),
('S04','Holybro Tekko32 F4 4in1 50A ESC','https://holybro.com/products/tekko32-f4-4in1-50a-esc','AM32 version and published connector drawing.'),
('S05','RadioMaster RP1 V2 receiver','https://radiomasterrc.com/products/rp1-expresslrs-2-4ghz-nano-receiver','RP1 V2 power, CRSF and antenna.'),
('S06','Matek M10Q-5883','https://www.mateksys.com/?portfolio=m10q-5883','Supply, UART, compass pads and separation guidance.'),
('S07','Dronetag BS gen.2 power connectors','https://help.dronetag.com/dronetag-bs-gen2/power-source-installation/','4-pin VCC/RX/TX/GND; second connector reserved contact.'),
('S08','VIFLY Finder 2','https://viflydrone.com/products/vifly-finder-v2-fpv-racing-drone-buzzer','5V/GND/BZ connection and self-powered function.'),
('S09','Feather Sense pinouts','https://learn.adafruit.com/adafruit-feather-sense/pinouts','Analog pins, power pins, A6 internal battery sense.'),
('S10','Feather Sense board files','https://github.com/adafruit/Adafruit-Feather-nRF52840-Sense-PCB','Revision-specific schematic and physical layout.'),
('S11','Feather nRF52840 Express pinouts','https://learn.adafruit.com/introducing-the-adafruit-nrf52840-feather/pinouts','Ground hub header pins and power.'),
('S12','Adafruit Short Flex Sensor #1070','https://www.adafruit.com/product/1070','Two-wire variable resistance sensor.'),
('S13','Adafruit protected 500 mAh LiPo #1578','https://www.adafruit.com/product/1578','Cell and charge compatibility.'),
('S14','Adafruit nRF52 Arduino analog implementation','https://github.com/adafruit/Adafruit_nRF52_Arduino/blob/master/cores/nRF5/wiring_analog_nRF52.c','Explicit ADC reference, resolution and acquisition settings.'),
('S15','RadioMaster Pocket','https://www.radiomasterrc.com/products/pocket-radio-controller-m2','DSC port and official manual; see trainer research for mono wiring.'),
('S16','EdgeTX trainer settings','https://manual.edgetx.org/bw-radios/radio-settings/trainer','Radio trainer calibration and mapping.'),
('S17','EdgeTX trainer validity source','https://github.com/EdgeTX/edgetx/blob/346c837d77d23932d860fe8b4c794b3f6ba074fb/radio/src/trainer.cpp','Reviewed source timeout; not a claim about installed radio firmware.'),
('S18','ArduPilot Kakute H7 documentation','https://ardupilot.org/copter/docs/common-holybro-kakuteh7.html','Serial mapping, battery scaling and output groups.'),
('S19','ArduPilot KakuteH7 hardware definition at reviewed commit','https://github.com/ArduPilot/ardupilot/blob/dbe792162d06cab66c3475fd5556bf7a120f119e/libraries/AP_HAL_ChibiOS/hwdef/KakuteH7/hwdef.dat','GPIO and UART verification; driver probes.'),
('S20','ArduPilot Crossfire and ELRS wiring','https://ardupilot.org/copter/docs/common-tbs-rc.html','Crossed full-duplex UART and protocol 23.'),
('S21','ArduPilot motor connection guide','https://ardupilot.org/copter/docs/connect-escs-and-motors.html','Motor identification and props-off motor tests.'),
('S22','ArduPilot motor matrix implementation','https://github.com/ArduPilot/ardupilot/blob/master/libraries/AP_Motors/AP_MotorsMatrix.cpp','BetaFlightX locations, directions and test order.'),
('S23','ArduPilot DShot setup','https://ardupilot.org/copter/docs/common-dshot-escs.html','Digital ESC configuration; no PWM endpoint calibration.'),
('S24','KakuteH7 current stable firmware record','https://firmware.ardupilot.org/Copter/stable/KakuteH7/','Reviewed 4.7.1 listing on 14 September 2026; recheck before installing.'),
('S25','TI SN74LVC1G125 datasheet','https://www.ti.com/lit/ds/symlink/sn74lvc1g125.pdf','Five-pin buffer, /OE, supply and power-off behavior.'),
('S26','RadioMaster official trainer port pinout','https://radiomasterrc.freshdesk.com/support/solutions/articles/64000256682-trainer-port-pin-out','Mono TS tip PPM / sleeve ground; family guidance, not Pocket input rating.'),
('S27','Adafruit SOT23 adapter #1230','https://www.adafruit.com/product/1230','Five-pin IC on six-pad carrier; verify leg-to-header continuity.'),
('S28','Holybro current sensor scale by ESC revision','https://docs.holybro.com/esc/current-sensor-scale','Convert Betaflight scale to A/V; received ESC revision determines value.'),
('S29','Pocket A1.8 official manual','https://cdn.shopify.com/s/files/1/0701/8066/7584/files/Pocket_A1.8.pdf?v=1770617495','DSC versus audio jack; independent batteries and SE momentary control.'),
('S30','Current Kakute H7 v1.5 diagram','https://cdn.shopify.com/s/files/1/0604/5905/7341/files/KAKUTE_H7_V1.5_diagram.jpg?v=1748308666','Physical pad/connector locator used in this package.'),
('S31','Matek cable and connector photo','https://www.mateksys.com/wp-content/uploads/2023/03/M10Q-5883_3.jpg','Supplied cable colors and module contact labels.'),
('S32','Dronetag connector front-view diagram','https://help.dronetag.com/img/dronetag-bs/4pin-diagram.jpg','Looking into board receptacle: 1 to 4 left-to-right as pictured.'),
('S33','EdgeTX logical-switch setup','https://manual.edgetx.org/bw-radios/model-select/logical-switches','Delay gating is a prototype proposal that needs actual-radio validation.'),
('S34','Dronetag gen.2 antenna installation','https://help.dronetag.com/dronetag-bs-gen2/enclosure-installation/','Bluetooth and GNSS antenna sockets are distinct.'),
('S35','Sense pin-to-GPIO variant','https://github.com/adafruit/Adafruit_nRF52_Arduino/blob/master/variants/feather_nrf52840_sense/variant.cpp','External pin names and internal A6 monitoring.'),
('S36','Express pin-to-GPIO variant','https://github.com/adafruit/Adafruit_nRF52_Arduino/blob/master/variants/feather_nrf52840_express/variant.cpp','D5/D6/D9 and battery monitor mapping.'),
('S37','Adafruit SOT23 carrier CAD','https://github.com/adafruit/Adafruit-SMT-Breakout-PCBs/blob/master/6-pin%20SOT-23.brd','Header-to-footprint mapping; IC pin5 uses carrier pad6.'),
('S38','EdgeTX PPM input decoder','https://github.com/EdgeTX/edgetx/blob/346c837d77d23932d860fe8b4c794b3f6ba074fb/radio/src/targets/common/arm/stm32/trainer_driver.cpp#L77','Channel and sync timing acceptance used for the proposed waveform.'),
('S39','Nordic nRF52840 product specification','https://docs-be.nordicsemi.com/bundle/nRF52840_PS_v1.8/raw/resource/enus/nRF52840_PS_v1.8.pdf','SAADC source resistance and acquisition time.'),
]

def intro():
    B.new('Full wiring schematic + build guide','A module-by-module assembly package for the attached 4S, two-hand BOM.', '00-system-overview')
    B.box(30,95,782,63,'WHAT THIS PACKAGE COVERS','Every external electrical connection in the selected aircraft, both five-finger sensor nodes and the ground hub. Commercial board internals are preassembled; solder to the labeled pads and headers shown here.',BLUE)
    # Topology with separate power domains.
    for x,title,body in [(30,'LEFT HAND - U6','Sense #4516\n5 flex channels\nBT2: protected 1S'),(30,'RIGHT HAND - U7','Sense #4516\n5 flex channels\nBT3: protected 1S')]:
        y=179 if 'LEFT' in title else 295;B.box(x,y,175,94,title,body,GREEN)
    B.box(287,227,173,107,'GROUND HUB - U8','Express #4062\nBT4: protected 1S\nPPM buffer + health checks',GREEN)
    B.box(523,227,125,107,'POCKET RADIO','Own 18650 cells\nDSC trainer input\nManual controls',PURPLE)
    B.box(712,179,100,210,'AIRCRAFT','RP1 V2\nCRSF\nKakute H7\nTekko ESC\n4 motors\nBT1: 4S',BLUE)
    B.arrow(205,221,287,249,GREEN,dash=[4,3]);B.text(230,217,'BLE',8,GREEN)
    B.arrow(205,337,287,302,GREEN,dash=[4,3]);B.text(230,345,'BLE',8,GREEN)
    B.arrow(460,281,523,281,PURPLE);B.text(489,271,'2 wires',8,PURPLE,align='center')
    B.arrow(648,281,712,281,BLUE,dash=[4,3]);B.text(680,270,'ELRS',8,BLUE,align='center')
    B.box(30,409,493,112,'BUILD STATUS','Aircraft and sensor wiring: component-documented design, ready for revision matching and bench assembly. Trainer buffer: a fully specified prototype circuit; Pocket input-level compatibility and radio fault handling still require bench validation. This is not a tested flight release.',ORANGE)
    B.box(541,409,271,112,'HOW TO READ','Solid lines = wires. Dashed arrows = radio links. Dots = joined wires. Same named net = connected conductor within that power domain. NC = leave unconnected. Colors are assembly suggestions; labels determine polarity.',BLUE)
    B.footer('Basis: S01. Four separate power domains; only the hub and Pocket share ground through their trainer cable.')

def baseline():
    B.new('01 / Freeze the exact build','The PDF BOM supersedes the older 3S / Kakute Mini / XIAO project documents for this package.')
    rows=[
      ['Aircraft controller / ESC','U1 Kakute H7 v1.5 + U2 Tekko32 F4 4in1 50A AM32','BOM D03, SKU 11091+31102; full-size 30.5 mm stack.'],
      ['Propulsion','4 x EMAX ECO II 2207 2400KV; P3B 5.1 x 3 x 2 props','BT1: one 1300 mAh 4S XT60 pack; 16.8 V when full.'],
      ['Aircraft peripherals','U3 RP1 V2; U4 M10Q-5883; U5 Dronetag BS gen.2; BZ1 Finder 2','All external power branches use regulated 5 V.'],
      ['Hands / hub','U6/U7 Sense #4516; U8 Express #4062; ten flex #1070','Three independent protected 1S cells #1578.'],
      ['UART allocation - design change','RP1 on R3/T3; GNSS on R4/T4; compass on SDA/SCL','Replaces provisional BOM UART1/3 allocation. Exposed pads avoid the 9 V VTX plug.'],
      ['Firmware basis','ArduCopter KakuteH7; reviewed stable listing 4.7.1','Confirm actual IMU/barometer detection before adopting the build.'],
      ['Motor convention - design choice','FRAME_CLASS=1; FRAME_TYPE=12 (BetaFlightX)','Physical channel numbers and motor-test letters are different; see sheet 05.'],
      ['Scope boundaries','No extra aircraft MCU, external hand IMU, camera or ToF board','The BOM has no obstacle-avoidance sensor package.'],
    ]
    B.table(30,95,[160,307,315],['Subsystem','Selected implementation','Build consequence'],rows,9.3,12,8)
    B.box(30,429,782,104,'QUICK NAVIGATION / PDF PAGE NUMBERS','Aircraft circuits and connectors: pages 3-9. Hand circuits, power and sensor checks: pages 10-15. Hub/trainer circuit and validation: pages 16-20. Firmware, parts, unused pins and build checks: pages 21-26. Sources: pages 27-29. Print landscape, fit to page; zoom the vector PDF for pad labels.',BLUE)
    B.footer('Sources: S01-S06, S09-S13, S18-S24. New interface passives and buffer are listed in the additions sheet.')

def aircraft_power():
    B.new('02 / Aircraft power + FC-to-ESC harness','Use the supplied matched 8-pin cable after continuity checking. B+ is raw battery voltage.', '02-aircraft-power')
    B.rect(32,124,147,176,PALE,LIGHT);B.text(45,145,'BT1 / XT60',13,INK,True)
    B.para(45,165,'4S 1300 mAh\n14.8 V nominal\n16.8 V full',122,10)
    B.text(164,239,'+',13,RED,True);B.text(164,282,'-',13,GND,True)
    B.rect(398,117,139,289,PALE,INK);B.text(410,140,'U2 / TEKKO',13,INK,True)
    B.text(410,157,'50A AM32',10,MUTED)
    B.text(410,237,'VBAT +',10,RED,True);B.text(410,283,'GND -',10,GND,True)
    B.line(179,235,398,235,RED,3);B.text(215,224,'P01  12 AWG red',9,RED)
    B.line(179,279,398,279,GND,3);B.text(211,295,'P02  12 AWG black',9,GND)
    B.line(300,235,300,248,RED);B.dot(300,235,RED)
    B.line(291,249,309,249,RED);B.line(291,256,309,256,GND);B.line(300,256,300,279,GND);B.dot(300,279,GND)
    B.text(313,251,'C1 1000 uF / 35 V',9,INK,True);B.text(313,265,'P03 + / P04 - stripe',8,MUTED)
    B.rect(687,117,125,289,PALE,INK);B.text(700,140,'U1 / KAKUTE',12,INK,True);B.text(700,157,'H7 v1.5 ESC1',10,MUTED)
    pins=[('VBAT','B+',RED),('TLM','R7',PURPLE),('GND','GND',GND),('CURRENT','CURRENT',ORANGE),('M1','M1',BLUE),('M2','M2',BLUE),('M3','M3',BLUE),('M4','M4',BLUE)]
    for i,(a,b,col) in enumerate(pins):
        y=187+i*27
        B.text(530,y+3,a,8.5,col,align='right');B.line(537,y,687,y,col,1.3)
        B.text(694,y+3,b,8.5,col);B.text(610,y-5,f'E{i+1:02}',8,MUTED,align='center')
    B.box(30,326,344,80,'DO NOT ADD A SMALL POWER SWITCH','Disconnect the XT60 to isolate the aircraft. The small wearable switches are only for Feather EN. BT1 balance plug remains disconnected in flight; use it only at the charger.',RED)
    B.box(30,429,371,101,'5 V POWER IS MADE ON THE FC','U2 passes battery voltage through E01. U1 regulates it. The receiver, GNSS, Remote ID and buzzer each take 5V + G from U1 (next sheet). Do not add a second 5 V supply in parallel.',BLUE)
    B.box(419,429,393,101,'PHYSICAL INSTALLATION','Keep the battery pair short and together. Mount C1 at U2 power pads with insulated leads and body restraint. Motor current flows through U2, not through the small harness or U1 ground pads.',BLUE)
    B.footer('Sources: S01-S04. Exact physical connector orientation is on sheet 04. Motor phase connections are on sheet 05.')

def peripheral_page():
    B.new('03 / Every aircraft peripheral wire','All pin names are board markings. UART wires cross: one board TX goes to the other board RX.', '03-aircraft-peripherals')
    B.rect(326,100,177,424,PALE,INK);B.text(339,120,'U1 KAKUTE H7 v1.5',12,INK,True)
    # Left receiver and navigation banks.
    B.rect(30,107,158,132,PALE,LIGHT);B.text(42,128,'U3 / RP1 V2',12,INK,True)
    for yy,label,pin,id,col in [(150,'5V','5V','A01',RED),(172,'GND','G','A02',GND),(194,'TX','R3','A03',BLUE),(216,'RX','T3','A04',PURPLE)]:
        B.text(180,yy+3,label,9,col,align='right');B.line(188,yy,326,yy,col,1.2);B.text(334,yy+3,pin,9,col);B.text(250,yy-5,id,8,MUTED)
    B.rect(30,270,158,190,PALE,LIGHT);B.text(42,291,'U4 / M10Q-5883',12,INK,True)
    for yy,label,pin,id,col in [(313,'5V','5V','A05',RED),(337,'G','G','A06',GND),(361,'TX','R4','A07',BLUE),(385,'RX','T4','A08',PURPLE),(409,'CL','SCL','A09',GREEN),(433,'DA','SDA','A10',ORANGE)]:
        B.text(180,yy+3,label,9,col,align='right');B.line(188,yy,326,yy,col,1.2);B.text(334,yy+3,pin,9,col);B.text(250,yy-5,id,8,MUTED)
    B.rect(635,107,177,144,PALE,LIGHT);B.text(647,128,'U5 / DRONETAG',12,INK,True)
    for yy,pin,label,id,col in [(151,'5V','1 VCC','A11',RED),(177,'G','4 GND','A12',GND)]:
        B.text(495,yy+3,pin,9,col,align='right');B.line(503,yy,635,yy,col,1.2);B.text(643,yy+3,label,9,col);B.text(563,yy-5,id,8,MUTED)
    B.para(647,201,'4-pin: 2 RX / 3 TX = NC\n3-pin socket: empty\nTwo marked RF antennas.',153,9)
    B.rect(635,281,177,137,PALE,LIGHT);B.text(647,302,'BZ1 / FINDER 2',12,INK,True)
    for yy,pin,label,id,col in [(325,'5V','5V','A13',RED),(354,'G','GND','A14',GND),(383,'Z-','BZ','A15',ORANGE)]:
        B.text(495,yy+3,pin,9,col,align='right');B.line(503,yy,635,yy,col,1.2);B.text(643,yy+3,label,9,col);B.text(563,yy-5,id,8,MUTED)
    B.para(340,466,'Repeated 5V and G labels share U1 rails. Use a soldered, insulated distribution joint if a pad cannot hold all branches. Do not crowd four wires onto one tiny pad.',149,8.5)
    B.para(30,482,'RP1: attach supplied 2.4 GHz antenna.\nMatek second socket + 3.3/RST pads: NC.\nU1 USB-C and microSD: plug-in service ports.',285,9)
    B.box(531,438,281,86,'Z- IS A SWITCHED SIGNAL','Finder 2 needs all three wires. Its GND goes to G, while BZ goes to Z-. Dronetag uses its own GNSS; no connection to U4.',ORANGE)
    B.footer('Sources: S03, S05-S08, S20. Use 26 AWG power/ground and 28 AWG signals; route compass away from motor/battery leads.')

def aircraft_schedule():
    B.new('Aircraft wire checklist','Check off by ID as each end is soldered, inspected and measured. Pads labeled G and GND are the same rail.')
    rows=[[w['id'],w['source'],w['destination'],w['wire'],w['notes']] for w in PERIPHERALS_DICT()]
    B.table(30,96,[45,157,151,107,322],['ID','From','To','Wire','Purpose / check'],rows,8.7,10.8,5.5)
    B.footer('Sources: S03, S05-S08. A wire-color mismatch is acceptable only when the pad-to-pad connection is positively identified.')

def PERIPHERALS_DICT():return [w for w in WIRES if w['id'].startswith('A')]

def hand_page(hand,ref):
    title='LEFT' if hand=='L' else 'RIGHT'
    B.new(f'06{hand} / {title.lower()} hand - five complete flex circuits',f'{ref}: Feather nRF52840 Sense #4516. Five circuits shown; build one independent circuit per finger.',f'06-{title.lower()}-hand')
    B.rect(648,101,164,379,PALE,INK);B.text(660,123,f'{ref} / {title} SENSE',12,INK,True)
    B.text(30,112,f'{ref} 3V',10,RED,True);B.line(47,122,47,461,RED,1.5)
    B.text(454,112,f'All ground symbols -> {ref} GND',8.5,GND)
    for i,finger in enumerate(FINGERS,1):
        y=145+(i-1)*63
        B.dot(47,y,RED);B.line(47,y,80,y,RED)
        # A detachable connector is represented by two labeled contacts around the flex path.
        B.circle(82,y,2.5,WHITE,RED);B.text(66,y-12,f'J{hand}{i}.1',8,MUTED)
        B.resistor(85,y,250,f'F{hand}{i} {finger} flex',GREEN)
        B.circle(252,y,2.5,WHITE,BLUE);B.text(240,y-12,f'J{hand}{i}.2',8,MUTED)
        B.line(255,y,648,y,BLUE,1.2);B.text(660,y+3,f'A{i-1}  /  {GPIO[i-1]}',9,BLUE)
        B.text(623,y-6,f'N{hand}{i}',8,BLUE)
        B.dot(315,y,BLUE);B.dot(455,y,BLUE)
        B.rv(315,y,y+40,f'R{hand}{i} 47k')
        B.capv(455,y,y+40,f'C{hand}{i} 100nF')
        B.line(315,y+40,555,y+40,GND);B.dot(455,y+40,GND);B.ground(555,y+40,hand+'_GND')
    B.text(660,451,'3V -> '+hand+'_3V bus',8.5,RED);B.text(660,466,'GND -> '+hand+'_GND bus',8.5,GND)
    B.box(30,487,379,48,'SENSOR HARNESS','J'+hand+'1..5: contact 1 = 3V, contact 2 = ADC. Label both halves. 30 AWG flexible leads.',GREEN)
    B.box(428,487,384,48,'POWER / BUTTON','BT'+('2' if hand=='L' else '3')+' + SW'+hand+' wiring is on sheet 07. '+('D5 = SW4 enable.' if hand=='L' else 'No external button on this hand.'),BLUE)
    B.footer('Sources: S01, S09-S14. RC parts sit by the Feather. 3V is regulated 3.3 V; do not connect these dividers to BAT or USB.')

def wearable_power():
    B.new('07 / Three independent batteries + two physical buttons','EN switches turn off the 3.3 V regulator; they do not disconnect the LiPo or disable the USB charger.', '07-wearable-power')
    for j,(label,ref,bt) in enumerate([('L','U6','BT2'),('R','U7','BT3'),('H','U8','BT4')]):
        x=30+j*267
        B.rect(x,100,248,269,PALE,LIGHT);B.text(x+12,121,f'{label}: {ref} + {bt}',12,INK,True)
        B.text(x+12,147,'#1578 protected 1S cell',9)
        B.rect(x+12,165,69,57,WHITE,INK);B.text(x+20,185,'LiPo',10,INK,True)
        B.text(x+74,185,'+',10,RED,align='right');B.text(x+74,211,'-',10,GND,align='right')
        B.rect(x+158,165,76,57,WHITE,INK);B.text(x+170,184,'JST BAT +',8.5,RED);B.text(x+170,210,'JST BAT -',8.5,GND)
        B.line(x+81,181,x+158,181,RED);B.text(x+111,175,label+'P1',8,RED)
        B.line(x+81,207,x+158,207,GND);B.text(x+111,220,label+'P2',8,GND)
        B.text(x+12,249,'EN',10,BLUE);B.line(x+35,246,x+96,246,BLUE);B.circle(x+96,246,2,WHITE,BLUE)
        B.line(x+98,246,x+132,231,BLUE);B.circle(x+135,246,2,WHITE,GND);B.line(x+137,246,x+194,246,GND);B.ground(x+194,246)
        B.text(x+202,262,label+'_GND',7,GND)
        B.text(x+83,276,'SW'+label+' OFF closes to GND',8.5)
        B.para(x+12,301,'Use common + one throw on a slide switch. Other throw NC. Open = ON. Feed no voltage into EN.',224,9)
    B.box(30,387,379,142,'SW4 - LEFT-HAND ENABLE','U6 D5 (P1.08) uses the filtered button circuit on sheet 07B. Pressed = LOW. Release must invalidate gesture authority in the hub. This is an input request, not a motor-power cut. A5 remains spare and A6 is the onboard battery monitor.',GREEN)
    B.box(428,387,384,142,'SW5 - HUB CALIBRATION','U8 D6 (P0.07) uses sheet 07B. Only accept calibration while radio gesture authority is OFF and aircraft disarmed. Use opposite contact groups of a 4-leg pushbutton; two legs from the same group are already connected.',BLUE)
    B.footer('Sources: S09-S13. Use onboard Micro-USB to program/charge; charge off the wearer. No separate charger board or shared battery rail.')

def hand_schedule():
    B.new('Hand circuit assembly checklist','All ten sensor connections are expanded on the two hand schematics; this table identifies the exact parts and nodes.')
    rows=[]
    for hand,ref in [('L','U6'),('R','U7')]:
        for i,finger in enumerate(FINGERS,1):
            rows.append([f'{hand}{i}a-f',f'{hand} {finger}',f'J{hand}{i}.1 = {ref} 3V\nJ{hand}{i}.2 = N{hand}{i}',f'{ref} A{i-1} ({GPIO[i-1]})',f'R{hand}{i}: 47k to {hand}_GND\nC{hand}{i}: 100nF to {hand}_GND'])
    B.table(30,95,[60,97,203,185,237],['Wire IDs','Finger','2-pin sensor connector','ADC connection','Node components'],rows,9.2,11.5,5)
    B.box(30,468,782,62,'IDENTICAL CIRCUIT; SEPARATE ELECTRICAL NODES','Do not join left and right 3V/GND rails. Do not join A0-A4 together. Each 47k resistor and each 100nF capacitor has its own ADC connection and returns to its local hand ground.',ORANGE)
    B.footer('The companion connection-list.md expands each a-f suffix into both component terminals. Connector pin numbers are project assignments.')

def adc_notes():
    B.new('08 / Sensor voltage + calibration checks','An ADC converts voltage to a number. Correct wiring still needs per-finger calibration and electrical fault checks.')
    B.box(30,96,379,118,'DIVIDER EQUATION','Vnode = 3.3 x 47000 / (Rflex + 47000). Example: 25k flex -> 2.154 V; 100k flex -> 1.055 V. These are calculated examples, not guaranteed straight/bent endpoints. Bending normally raises resistance and lowers voltage.',GREEN)
    B.box(428,96,384,118,'ADC SETUP - ADAFRUIT nRF52 ARDUINO','Set analogReadResolution(12), analogReference(AR_INTERNAL), analogSampleTime(10). The internal configuration uses a nominal 3.6 V full scale. Confirm your installed core API. 3.3 V is about 3754/4095, not 4095.',BLUE)
    B.table(30,232,[166,163,453],['Condition','Expected electrical reading','Required action'],[
      ['Sensor unplugged / broken','Near 0 V through 47k','Invalidate channel before normalization; do not interpret as maximum curl.'],
      ['Flex shorted','Near 3.3 V','Reject against calibrated electrical bounds; rail faults must not create maximum command.'],
      ['Normal mounted movement','Measure each channel','Store open and comfortable-curled values with channel/hand identity. Reject insufficient span.'],
      ['Battery monitoring','A6 is already connected','Use onboard divider and board-specific conversion. A6 is not a spare external finger input.'],
      ['100nF settling','Max Rth <=47k; tau <=4.7 ms','Calculated RC bound. Filter latency adds to radio delay; measure whole-chain response.'],
    ],9.4,12.2,7)
    B.para(30,494,'Mechanical routing: allow the sensor strip to slide in a guide. Do not cut it, fold its terminal area or rigidly glue both ends to a finger. Keep the soldered ends off bending joints and insulate them from skin.',782,10)
    B.footer('Sources: S01, S09-S14 and Nordic SAADC guidance in docs/schematic-research-hands.md. Firmware and calibration are required work.')

def connectors():
    B.new('04 / FC and ESC connector orientation','View the actual component face. Cable wire-entry views are mirrored; continuity-test by function.', '04-stack-connectors')
    B.rect(30,99,365,202,PALE,LIGHT);B.text(43,120,'U1 TOP VIEW - USB-C ON RIGHT',11,BLUE,True)
    B.rect(130,178,170,99,WHITE,INK);B.rect(296,217,25,32,LIGHT,INK);B.text(332,236,'USB',9)
    B.text(130,292,'ESC1 is the top connector',9,MUTED)
    # The eight indexes are this document's contact identifiers, not JST standard numbers.
    names=['B+','R7','GND','CUR','M1','M2','M3','M4']
    for i,name in enumerate(names):
        xx=91+i*35;B.rect(xx,152,31,22,WHITE,INK);B.text(xx+15,146,f'c{i+1}',8,MUTED,align='center');B.text(xx+15,167,name,8,RED if i==0 else INK,align='center')
    B.rect(417,99,395,202,PALE,LIGHT);B.text(431,120,'U2 TOP VIEW - BATTERY PADS LEFT',11,BLUE,True)
    B.rect(489,140,159,147,WHITE,INK);B.text(476,196,'-',15,GND,True);B.text(476,235,'+',15,RED,True)
    for i,name in enumerate(['VBAT','TLM','GND','CURRENT','M1','M2','M3','M4']):
        y=143+i*18;B.rect(647,y,12,14,WHITE,INK);B.text(667,y+11,f'c{i+1}  {name}',8,RED if i==0 else INK)
    B.text(504,161,'M3 bank',9);B.text(591,161,'M4 bank',9)
    B.text(504,276,'M1 bank',9);B.text(591,276,'M2 bank',9)
    rows=[]
    for i,w in enumerate([w for w in WIRES if w['id'].startswith('E')],1):rows.append([f'c{i} / {w["id"]}',w['source'].replace('U2 harness ',''),w['destination'].replace('U1 ESC1 ',''),w['notes']])
    B.table(30,315,[75,112,112,483],['Contact / ID','ESC end','FC ESC1 end','Continuity check'],rows,8.8,10.7,4.8)
    B.footer('Sources: S03-S04, S30. c1-c8 are project contact indexes tied to these views. U1 ESC2 (M5-M8) remains EMPTY.')

def motor_page():
    B.new('05 / Twelve motor wires + fixed motor order','Top view, nose up. This drawing requires ArduPilot BetaFlightX (FRAME_TYPE 12), not default Quad X.', '05-motor-wiring')
    B.arrow(262,172,262,112,BLUE,2);B.text(278,133,'NOSE',10,BLUE,True)
    B.rect(178,223,165,118,PALE,INK);B.text(260,246,'U2 / 4-in-1 ESC',11,INK,True,align='center')
    B.text(260,270,'M1 - M4 banks',10,INK,align='center');B.text(260,292,'3 phase pads per bank',9,MUTED,align='center')
    # Every phase lead is drawn individually and assigned a wire ID.
    motors=[(4,98,157,'FRONT LEFT','CW',178,239),(2,422,157,'FRONT RIGHT','CCW',343,239),(3,98,405,'REAR LEFT','CCW',178,326),(1,422,405,'REAR RIGHT','CW',343,326)]
    for n,x,y,pos,direction,ex,ey in motors:
        B.circle(x,y,37,WHITE,BLUE,1.5);B.text(x,y-2,f'M{n}',16,BLUE,True,align='center');B.text(x,y+15,direction,10,INK,True,align='center')
        B.text(x,y-50,pos,9,INK,True,align='center')
        for p,label in enumerate('UVW'):
            sx=x+(31 if x<260 else -31);sy=y+(p-1)*9
            ee=ey+(p-1)*9;B.line(sx,sy,ex,ee,[BLUE,GREEN,ORANGE][p],1.3)
        B.text(x,y+54,f'M{n}U / M{n}V / M{n}W',8,MUTED,align='center')
    B.box(503,99,309,111,'THE SELECTED MOTOR MIX','FRAME_CLASS = 1 (Quad)\nFRAME_TYPE = 12 (BetaFlightX)\nSERVO1_FUNCTION = 33; SERVO2 = 34\nSERVO3_FUNCTION = 35; SERVO4 = 36',BLUE)
    B.table(503,226,[48,84,67,110],['Bank','Location','Turn','Motor test'],[
      ['M1','Rear right','CW','B'],['M2','Front right','CCW','A'],['M3','Rear left','CCW','C'],['M4','Front left','CW','D'],
    ],9.1,11.5,7)
    B.box(503,400,309,127,'PHASE CONNECTION RULE','Mark each motor lead U/V/W and connect all three to one numbered bank. The three leads have no + or -. If the motor turns the wrong way, change AM32 direction or swap any two phases. Verify direction viewed from above, with props removed.',ORANGE)
    B.para(30,487,'The physical ESC board can rotate to suit the wiring. Bank labels, not the apparent corner of the ESC board, choose the motor. Keep the FC orientation arrow toward the nose or configure its measured rotation.',447,9.5)
    B.footer('Sources: S04, S18, S21-S23. Install CW/CCW propellers only after motor identity and direction both pass.')

def connector_details():
    B.new('Connector detail / GPS, receiver and Remote ID','Use supplied harnesses wherever possible. Colors shown below come from manufacturer photos; verify the received cable.')
    B.table(30,97,[104,98,102,118],['Matek contact','Cable color','FC pad','Function'],[
        ['5V','Red','5V','Power'],['RX','Yellow','T4','Into GNSS'],['TX','Blue','R4','Out of GNSS'],
        ['CL','Green','SCL','I2C clock'],['DA','White','SDA','I2C data'],['G','Black','G','Ground'],
    ],9.3,11.8,6)
    B.box(30,330,422,107,'MATEK HAS TWO MIRRORED SOCKETS','Use one 6-pin GH connector only. In the maker underside view, supercapacitor upper-right: left socket top-to-bottom = 5V/RX/TX/CL/DA/G; right socket is reversed. Spare socket and utility 3.3/RST pads remain unused.',ORANGE)
    B.image(ASSETS/'dronetag-4pin.jpg',479,99,326,237)
    B.text(480,350,'Dronetag: looking INTO the board socket',10,BLUE,True)
    B.para(480,372,'Four-pin port: 1 VCC -> FC 5V; 4 GND -> FC G. Pins 2 RX and 3 TX are insulated and unused. Three-pin port remains empty. Figure: Dronetag, S32.',326,10)
    B.box(30,452,422,78,'RP1 V2 PAD VIEW','Antenna/U.FL side shown by RadioMaster: RX / TX / 5V / G. Reverse face is mirrored. Use actual pad text: TX -> R3, RX -> T3, 5V -> 5V, G -> G.',BLUE)
    B.box(470,452,342,78,'FINDER 2 / STOCK HARNESS','Red 5V -> FC 5V; black GND -> FC G; yellow BZ -> FC Z-. Its connector cavity numbering is not assumed. Keep its disarm button accessible.',BLUE)
    B.footer('Sources: S05-S08, S31-S32. GH on Matek is 1.25 mm family; SH on Holybro/Dronetag is 1.0 mm. Same contact count does not imply fit.')

def button_page():
    B.new('07B / Two filtered button circuits','These passives are additional to the ten flex-divider networks. Each circuit uses its own local 3.3 V and ground.', '07b-buttons')
    for j,(ref,gpio,sw,pull,series,cap,rail,title) in enumerate([
      ('U6','D5 / P1.08','SW4','R201','R202','C201','L','HOLD TO ENABLE'),
      ('U8','D6 / P0.07','SW5','R203','R204','C202','H','CALIBRATE'),
    ]):
        y=111+j*196
        B.rect(30,y,782,177,PALE,LIGHT);B.text(45,y+22,title,12,BLUE,True)
        B.text(51,y+70,ref+' 3V',10,RED,True)
        B.resistor(113,y+66,258,pull+' 10k',RED);B.dot(258,y+66,BLUE)
        B.line(258,y+66,258,y+37,BLUE);B.line(258,y+37,440,y+37,BLUE);B.text(446,y+41,ref+' '+gpio,10,BLUE,True)
        B.resistor(258,y+66,455,series+' 1k',BLUE)
        B.circle(455,y+66,2,WHITE,BLUE);B.line(457,y+66,490,y+50,BLUE);B.circle(494,y+66,2,WHITE,GND)
        B.line(496,y+66,570,y+66,GND);B.ground(570,y+66,rail+'_GND');B.text(469,y+95,sw+' normally open',9)
        B.capv(258,y+66,y+125,cap+' 100nF');B.ground(258,y+125,rail+'_GND')
        B.para(635,y+40,'GPIO mode: INPUT. Open ~3.3 V. Pressed ~0.30 V. Start with 20 ms software debounce.',158,9.5)
    B.para(30,520,'A short-to-ground can imitate a press: require release-then-press after boot/reconnect. Physical radio takeover remains independent.',782,9.5)
    B.footer('Design-selected circuit; pin verification S35-S36. All resistors 1%, >=0.125 W; capacitors X7R >=10 V.')

def trainer_page():
    B.new('09 / Ground hub-to-Pocket buffer - complete prototype','JP301 stays OPEN until the actual Pocket trainer input is confirmed compatible with the proposed 3.3 V signal.', '09-trainer-buffer')
    B.box(30,97,782,49,'BENCH PROTOTYPE - ELECTRICAL INPUT RATING NOT YET VERIFIED','The mono TS tip/sleeve assignment is documented at RadioMaster family level. Pocket-specific voltage limits were not found.',ORANGE)
    B.rect(30,197,173,214,PALE,INK);B.text(44,222,'U8 / EXPRESS #4062',11,INK,True)
    B.rect(418,193,168,220,PALE,INK);B.text(430,218,'U301',13,INK,True);B.text(430,235,'SN74LVC1G125DBVR',9,INK)
    # Supply, input and output enable links with separate named ground returns.
    B.text(44,264,'3V',10,RED,True);B.line(203,260,418,260,RED);B.text(426,264,'5 VCC',10,RED)
    B.text(44,304,'D9 / P0.26',10,PURPLE);B.line(203,300,418,300,PURPLE);B.text(426,304,'1 /OE',10,PURPLE)
    B.dot(275,260,RED);B.rv(275,260,300,'R301 10k');B.dot(275,300,PURPLE)
    B.text(44,351,'D5 / P1.08',10,BLUE);B.line(203,347,418,347,BLUE);B.text(426,351,'2 A',10,BLUE)
    B.dot(332,347,BLUE);B.rv(332,347,399,'R302 100k');B.ground(332,399,'H_GND')
    B.text(44,392,'GND -> H_GND',10,GND);B.text(426,392,'3 GND',10,GND);B.line(474,399,474,424,GND);B.ground(474,424,'H_GND')
    B.text(543,326,'4 Y',10,BLUE);B.resistor(586,322,703,'R303 1k',BLUE)
    B.circle(709,322,2.5,WHITE,BLUE);B.circle(731,322,2.5,WHITE,BLUE);B.text(716,294,'JP301',9,ORANGE,True,align='center');B.text(716,309,'OPEN',8,ORANGE,align='center')
    B.line(703,322,706,322,BLUE);B.line(734,322,794,322,BLUE);B.text(795,341,'TS TIP',9,BLUE,True,align='right')
    B.text(700,344,'TP301',7.5,MUTED,align='right');B.text(738,344,'TP302',7.5,MUTED)
    B.text(657,380,'J301: 3.5 mm MONO TS',9,INK,True);B.line(646,399,794,399,GND);B.ground(646,399,'H_GND');B.text(793,392,'SLEEVE',9,GND,align='right')
    # Decoupling drawn separately with explicit matching net labels to avoid crossings.
    B.text(644,175,'C301 at U301 pins 5/3',9,INK,True);B.text(682,197,'H_3V',8,RED);B.capv(695,204,254,'100nF');B.ground(695,254,'H_GND')
    B.box(30,456,382,75,'BUFFER BEHAVIOR','D9 HIGH disables the output; D9 LOW enables it. R301 defaults to disabled at reset. Initialize D5 LOW and D9 HIGH before starting valid timing. The buffer is not isolation.',BLUE)
    B.box(429,456,383,75,'CABLE / POWER','Connect only TIP = PPM and SLEEVE = ground. No radio power wire. Use a short shielded cable. Hub has BT4; Pocket retains its own cells. Add no capacitor to the PPM output.',BLUE)
    B.footer('Sources: S11, S25-S27, S29, S36-S37. Full 14-wire buffer netlist is on the following sheet; power/button circuits on 07 / 07B.')

def trainer_schedule():
    B.new('Trainer buffer connection checklist','Package-specific pin numbers refer to TI SN74LVC1G125DBVR, top view, SOT-23-5.')
    rows=[[w['id'],w['source'],w['destination'],w['notes']] for w in WIRES if w['id'] in [x[0] for x in TRAINER]]
    B.table(30,95,[45,188,222,327],['ID','From','To','Assembly detail'],rows,8.9,11,5.8)
    B.footer('Source: S25. H01-H14 here are wire IDs, independent of the H01-H11 purchasing line IDs in the source BOM.')

def carrier_page():
    B.new('09B / Buffer carrier + trainer plug detail','The five-pin IC and a six-pad adapter do not have matching pin numbers at the upper-right position.', '09b-buffer-carrier')
    B.rect(30,97,375,299,PALE,LIGHT);B.text(45,120,'ADAFRUIT #1230 SOT23 FRONT',11,BLUE,True)
    B.rect(145,171,126,160,WHITE,INK);B.rect(174,197,71,102,INK,INK);B.circle(184,208,3,WHITE,WHITE)
    for y,ic,func,pad in [(202,1,'/OE',1),(247,2,'A',2),(292,3,'GND',3)]:
        B.rect(152,y-4,22,8,LIGHT,INK);B.text(142,y+4,f'{ic} {func}',9,INK,align='right');B.text(67,y+18,f'pad {pad}',8,MUTED)
    for y,ic,func,pad in [(202,5,'VCC',6),(292,4,'Y',4)]:
        B.rect(245,y-4,22,8,LIGHT,INK);B.text(277,y+4,f'{ic} {func}',9,INK);B.text(332,y+18,f'pad {pad}',8,MUTED)
    B.rect(250,243,17,8,WHITE,LIGHT);B.text(277,251,'EMPTY (pad 5)',8.5,ORANGE)
    B.text(208,347,'SOT23 text at bottom',9,MUTED,align='center')
    B.para(46,371,'Use the SOT23-5/6 face. Pin-1 dot orientation is critical.',343,9.5)
    B.table(431,99,[117,126,138],['IC pin','Carrier pad','Header hole'],[
      ['1 /OE','1','JP2.1'],['2 A','2','JP2.2'],['3 GND','3','JP2.3'],['4 Y','4','JP1.3'],['5 VCC','6','JP1.1'],['No IC lead','5','JP1.2 unused'],
    ],9.4,12,7)
    B.box(431,341,381,55,'VERIFY BEFORE SOLDERING TO U8','Meter from each IC leg to its header. Carrier hole numbers do not equal five-pin IC numbers.',ORANGE)
    B.rect(30,419,782,111,PALE,LIGHT);B.text(45,442,'MONO TS PLUG - TWO ELECTRICAL CONTACTS',11,BLUE,True)
    B.rect(63,470,194,26,LIGHT,INK);B.rect(258,470,7,26,INK,INK);B.rect(265,470,64,26,WHITE,INK)
    B.text(158,487,'SLEEVE = H_GND',10,INK,True,align='center');B.text(297,487,'TIP',10,BLUE,True,align='center')
    B.para(365,471,'One insulating band = TS. Use the Pocket DSC port. Tip -> JP301.2; sleeve -> U8 GND. A headphone TRS cable is not the selected cable.',428,10)
    B.footer('Sources: S25-S27, S29, S37. Diagram is a connection locator, not a fabrication footprint or scale drawing.')

def timing_page():
    B.new('10 / Required trainer waveform + authority logic','These are firmware and radio configuration requirements. Wiring alone cannot implement or validate them.')
    B.table(30,96,[88,238,456],['Trainer slot','Meaning','Proposed frame value'],[
      ['TR1 / TR2','Roll / pitch','1000-2000 us; neutral 1500 us; bounded mapping'],
      ['TR3 / TR4','Throttle / yaw','Throttle semantics must match FC flight mode; yaw neutral 1500 us'],
      ['TR5','HAND DATA VALID','1000 us invalid; 2000 us valid; this is not the aircraft arm channel'],
      ['TR6','Application heartbeat','1000/2000 us alternating every 2 NEW frames using fresh data from BOTH hands'],
      ['TR7 / TR8','Reserved','1500 us; do not assign to arm or emergency control'],
    ],9.4,12,6)
    B.box(30,299,379,118,'PPM TIMING - BENCH DESIGN','8 channels, 22,500 us frame, 300 us active-high markers. Each channel interval is rising-edge to rising-edge, 1000-2000 us. Sync interval = 22500 - sum(all 8 channel intervals), leaving at least 6500 us.',BLUE)
    B.box(428,299,384,118,'POCKET SETUP REQUIREMENT','Master/Jack. Calibrate and map TR1-4 to Ail/Ele/Thr/Rud. Replace those four axes only while the authority gate is true. Arm and flight modes stay on deliberate Pocket physical controls.',PURPLE)
    B.box(30,435,782,98,'DO NOT RELY ON TRAINER-LOSS TIMEOUT ALONE','Reviewed EdgeTX source permits about 1 second before trainer invalidation. Require: SE held + trainer present + TR5 valid + recently changed TR6 + no latched fault. Gate failure returns to manual sticks. Require release/re-enable after recovery. A timer must not replay old commands and heartbeat forever.',ORANGE)
    B.footer('Sources: S16-S17, S26, S29, S33, S38. Exact EdgeTX model and MCU firmware remain to be implemented and bench-qualified.')

def trainer_validation():
    B.new('Trainer validation / the remaining interface gate','A DMM idle-voltage measurement alone does not establish the Pocket input rating.')
    rows=[
      ['1 / Hub alone','JP301 removed; Pocket disconnected','Check 3.3 V on U301 pins 5/3. /OE HIGH at reset. Verify waveform at TP301 with a high-impedance scope.'],
      ['2 / Input compatibility','RadioMaster information or competent circuit examination','Confirm actual Pocket input VIH/VIL and permitted voltage/current. Radio Slave/Jack output can be observed as evidence, but does not prove input tolerance.'],
      ['3 / Connect only after step 2','Both devices OFF; 3.3 V compatibility established','Fit JP301 shunt; connect TS sleeve/ground and tip; set Master/Jack. Power up and inspect loaded waveform at TP302. Do not raise signal to 5 V without a specification.'],
      ['4 / Channel mapping','Props OFF; FC channel monitor open','Check all four axes, sign, neutral and limits. Verify physical arm/mode controls remain independent.'],
      ['5 / Freeze/loss','Inject stopped and repeated-old PPM','Test each hand off, hub reset/freeze, stuck-high and stuck-low heartbeat, cable removal and radio restart. Measure time until FC receives manual input.'],
      ['6 / Recovery','SE held during reconnection','Gestures must stay disabled until SE is released and deliberately re-enabled. Match manual throttle before takeover to avoid a step in commanded thrust.'],
    ]
    B.table(30,98,[107,212,463],['Stage','Setup','Pass evidence'],rows,9.4,12.2,8)
    B.box(30,452,782,80,'HEARTBEAT GATE CANDIDATE - TEST, DO NOT ASSUME','Two level checks on TR6 (>0 and <0), each with Delay 0.1 s and Duration 0, OR together as heartbeat_stuck. A healthy 45 ms half-cycle prevents either delay completing. Also require trainer-present and TR5 valid; latch authority faults until SE release. Validate installed EdgeTX timing and startup behavior.',ORANGE)
    B.footer('Sources: S17, S25-S26, S29, S33. Exact trainer circuit and receiver firmware behavior still need real hardware evidence.')

def firmware_page():
    B.new('11 / ArduPilot setup that matches these wires','Save the original parameters first. Reboot after serial, frame and motor-output changes; verify each result with props off.')
    rows=[
      ['Firmware target','KakuteH7','Reviewed stable listing: ArduCopter 4.7.1. Confirm detected ICM-42688-P and SPA06/barometer behavior on received v1.5.'],
      ['RP1 on R3/T3','SERIAL3_PROTOCOL=23; SERIAL3_OPTIONS=0','Use receiver CRSF output. Crossed full-duplex UART. RC protocol controls baud; verify telemetry and no UART3 GPS assignment.'],
      ['GNSS on R4/T4','SERIAL4_PROTOCOL=5; SERIAL4_OPTIONS=0','GPS automatic configuration enabled; use the matching GPS type/driver. Matek factory UART 9600; verify autoconfiguration.'],
      ['ESC telemetry on R7','SERIAL7_PROTOCOL=16','TLM wire from U2. Enable/request AM32 telemetry as required by installed firmware, then verify logged data.'],
      ['Unused UARTs','UART1, UART6 external functions unused','Keep UART2 reserved for onboard Bluetooth; do not add another peripheral there. Disable unused model assignments.'],
      ['Frame and output order','FRAME_CLASS=1; FRAME_TYPE=12','SERVO1/2/3/4_FUNCTION = 33/34/35/36. Motor test A=FR, B=RR, C=RL, D=FL.'],
      ['Digital motor commands','MOT_PWM_TYPE: select DShot300 (value 5)','Verify DShot mode after reboot; no throttle endpoint ESC calibration. Leave reversible/3D operation disabled.'],
      ['Battery monitor','BATT_MONITOR=4; BATT_VOLT_PIN=10; BATT_CURR_PIN=11','BATT_VOLT_MULT=11 is a starting value; measure and calibrate. Current scale depends on ESC revision (next sheet).'],
      ['Radio channel contract','CH1 roll, CH2 pitch, CH3 throttle, CH4 yaw','Set and verify RCMAP accordingly. Physical radio arm/mode channels are separate from trainer TR5/TR6 health slots.'],
    ]
    B.table(30,96,[126,251,405],['Function','Configuration basis','What to verify'],rows,8.9,11.2,6)
    B.footer('Sources: S18-S24, S28. This is an interface checklist, not a complete flight tune or a prevalidated parameter file.')

def power_budget():
    B.new('12 / Current scaling + power-rail acceptance','The ESC PCB revision determines analog current conversion; the flight-controller v1.5 label does not determine it.')
    B.table(30,95,[192,143,179,268],['Tekko 31102 ESC revision','Maker BF scale','ArduPilot A/V start value','Action'],[
      ['v1.5 / v1.6 / v1.7','168','59.524','Read actual ESC silkscreen; then calibrate.'],
      ['v1.8','110','90.909','10000 / BF scale.'],
      ['v1.9 / v1.9T','120','83.333','Set BATT_AMP_PERVLT appropriately.'],
    ],9.5,12,8)
    B.box(30,237,782,71,'5 V RAIL DESIGN LIMIT','Current Holybro v1.5 material says 2 A; the older pin table says 1.5 A. Until received hardware and thermal performance are verified, use a conservative ceiling below 1.5 A for the total measured 5 V load, including FC consumption as applicable. This is a design limit, not a measured load.',ORANGE)
    B.table(30,324,[180,200,200,202],['Load','Published starting information','Record peak current','Check at startup / hot condition'],[
      ['FC U1','Measure on actual revision','_____ mA','5 V source and board temperature'],
      ['RP1 U3','5 V supply; peak not established here','_____ mA','Telemetry activity; no reset'],
      ['Matek U4','About 13 mA nominal (not peak)','_____ mA','Startup and GNSS acquisition'],
      ['Dronetag U5','Reserve >=50 mA until measured','_____ mA','Broadcast and GNSS acquisition'],
      ['Finder BZ1','Measure buzzer + backup-cell charging','_____ mA','Buzzer active with cell charging'],
      ['TOTAL + margin','Confirm below selected ceiling','_____ mA','No load below its required input voltage'],
    ],9.1,11.5,5.5)
    B.footer('Sources: S02, S04-S08, S28. Component ratings do not establish aircraft maximum current or endurance.')

def additions_page():
    B.new('13 / Small parts to make the circuit complete','These specify the BOM allowances for H05/H06/H07/H10. Check included harnesses before purchasing duplicates.')
    B.table(30,96,[197,62,228,295],['Part / reference','Qty','Specification','Where used'],[
      ['RL1-RL5, RR1-RR5','10','47 kohm, 1%, >=0.125 W','One shunt resistor per flex channel'],
      ['CL1-CL5, CR1-CR5','10','100 nF X7R ceramic, >=10 V','ADC node to local ground'],
      ['R201 / R203 / R301','3','10 kohm, 1%, >=0.125 W','Two button pull-ups + buffer /OE pull-up'],
      ['R202 / R204 / R303','3','1 kohm, 1%, >=0.125 W','Two button series resistors + PPM output'],
      ['R302','1','100 kohm, 1%, >=0.125 W','PPM input pull-down'],
      ['C201 / C202 / C301','3','100 nF X7R, >=10 V','Two button filters + buffer decoupling'],
      ['U301 + carrier','1 each','SN74LVC1G125DBVR + Adafruit #1230','SOT23-5 buffer; inspect pin-5/pad-6 mapping'],
      ['JP301','1','2-pin 2.54 mm header + removable shunt','Trainer qualification break point'],
      ['J301','1','3.5 mm male MONO TS + short shielded cable','Pocket DSC signal and ground only'],
      ['JL1-5 / JR1-5','10 pairs','Keyed 2-contact connector pairs','Pin 1 regulated 3V; pin 2 finger signal; mark each housing'],
      ['SWL / SWR / SWH','3','Maintained SPST or SPDT slide','EN to GND OFF; unused throw NC'],
      ['SW4 / SW5','2','Normally open momentary pushbuttons','Left enable; hub calibration'],
      ['Prototyping / wire','3 sets','Solderable boards, headers and heat-shrink','26 AWG low-voltage power; 28-30 AWG signals; label both ends'],
    ],8.9,11.1,5.3)
    B.footer('Sources: S01, S25, S27. Select voltage-rated insulated connector parts. No solderless breadboard or loose Dupont lead in a flying build.')

def nc_page():
    B.new('14 / Unused pins + service connections','NC means deliberately leave open; an unused power output must not be shorted to ground.')
    B.table(30,96,[152,344,286],['Board / connector','Leave unused in this revision','Connect / preserve'],[
      ['Kakute U1','ESC2; VTX plug; Vi/Vo/CAM; 9V; 3v3; RSI; LED; R6/T6','ESC1, UART3/4, SDA/SCL, 5V/G/Z-. USB-C and microSD for setup/logging.'],
      ['Matek U4','Second mirrored GH socket; utility 3.3/RST pads','One GH cable with all six named wires. Built-in GNSS antenna faces sky.'],
      ['Dronetag U5','4-pin UART RX/TX individually insulated; entire 3-pin port','4-pin VCC/GND only. Both supplied RF antennas in matching sockets.'],
      ['U6 / U7 Sense','A5, AREF, SCK/MOSI/MISO, TX/RX, 2/6/9/10/11/12/13, SDA/SCL externally; U7 D5','A0-A4 flex, 3V/GND, EN, native battery JST. U6 D5 button. Built-in sensors stay internally wired.'],
      ['U8 Express','A0-A5, AREF, SPI, TX/RX, 2/10/11/12/13, SDA/SCL externally','D5 waveform, D9 /OE, D6 button, 3V/GND/EN, native JST and Micro-USB.'],
      ['All Feathers','BAT / USB header pads need no extra wire; do not repurpose internal A6','Native Micro-USB data cables for programming and own-board charging. Do not add another charger.'],
      ['BT1 flight pack','Balance lead disconnected from aircraft in flight','Main XT60 to ESC; charger separately uses appropriate main and balance connections.'],
      ['Pocket','Headphone jack, module bay and USB not part of trainer harness','Own correct-polarity 18650 cells; original internal ELRS antenna; DSC TS cable only.'],
    ],9.0,11.5,6)
    B.footer('Sources: S01-S13, S29, S35-S36. Factory onboard traces, antennas, chargers and sensors are not extra user wiring.')

def assembly_page():
    B.new('15 / Build order + first power-up','Complete each stage before closing the enclosure. Propellers remain removed throughout these electrical checks.')
    B.table(30,96,[51,221,510],['Step','Assemble','Check before continuing'],[
      ['1','Label all received parts','Record FC/ESC revision and firmware. Mark front of aircraft and M1-M4 locations. Select exact 4S/2400KV parts.'],
      ['2','Main power P01-P04','Battery disconnected: verify XT60/capacitor polarity, no solder bridge, insulation and strain relief. Brief capacitor charging can affect resistance reading; persistent low resistance needs diagnosis.'],
      ['3','ESC1 cable E01-E08','Cable disconnected from both boards: meter all eight function-to-function connections and check adjacent wires for shorts. Plug into ESC1 only.'],
      ['4','FC + ESC electronics only','Use appropriate XT60 smoke stopper/current limit. Check for heating, supply voltage and stable FC boot. Do not use smoke stopper for propulsion loading.'],
      ['5','Add A01-A15 one device at a time','Measure 5 V at each load, attach RF antennas before power, verify RP1 channels, GNSS, compass and buzzer. Recheck under combined load.'],
      ['6','Build one flex channel first','Meter 3.3 V, ADC node and flex variation. Then add other nine circuits. No A0-A4 shorts; verify unplugged sensor behavior.'],
      ['7','Add batteries, switches and buttons','EN closed = regulator off. Check each battery plug polarity. Verify enable release, calibration restrictions and correct hand identity.'],
      ['8','Build U301 carrier / hub','JP301 OPEN. Verify five IC pins, supply, reset disable and scope waveform. Complete the Pocket compatibility gate before joining trainer output.'],
      ['9','Connect M1-M4 phase leads','Props off: identify every motor-test letter and direction. Inspect motor screw clearance into windings. Save wiring and parameter records.'],
    ],9.1,11.5,6.5)
    B.footer('Use the matching manufacturer manuals for initial firmware loading. Wiring checks do not replace the structural/propulsion tests in the source BOM.')

def acceptance_page():
    B.new('16 / Test points + completion record','Write measured values and save photos of the completed harness. These criteria identify wiring faults before flight testing.')
    B.table(30,96,[73,188,276,245],['Point','Measure relative to','Expected / required evidence','Record'],[
      ['TP-BAT','U2 VBAT to U2 GND','Matches connected 4S pack; at most 16.8 V when fully charged','_____ V'],
      ['TP-5V','U1 5V to G and each load','Regulated near 5 V; no out-of-range sag or resets under peak load','source _____ / load _____ V'],
      ['TP-L3V','U6 3V to U6 GND','Near 3.3 V with SWL open; shuts down with EN grounded','_____ V'],
      ['TP-R3V','U7 3V to U7 GND','Same independent test with SWR','_____ V'],
      ['TP-H3V','U8 3V to U8 GND','Same independent test; U301 pins 5/3 same supply','_____ V'],
      ['NL1-NR5','Each ADC node to own GND','Distinct per-finger ranges; unplugged near 0 V; no crossed channels','Calibration file: __________'],
      ['TP301','JP301.1 to H_GND','Hub-only PPM levels, timing, reset/fault behavior; shunt out','Scope capture: __________'],
      ['TP302','JP301.2 to H_GND','After input qualification: loaded Pocket signal and correct decoded channels','Radio revision: __________'],
    ],9.2,11.7,6.5)
    B.box(30,433,782,100,'REMAINING RELEASE EVIDENCE','Trainer voltage compatibility and takeover timing; both-hand firmware + radio model; received ESC current scaling; FC sensor detection; measured 5 V peak load; GPS/compass placement and motor-current interference. Matek requests 100 mm separation from power wiring, ESCs, motors and ferrous material. The current compact GPS deck does not establish that clearance.',ORANGE)
    B.footer('This package specifies a buildable module interconnect and a conditional trainer prototype. It is not an ERC/PCB fabrication file or proof of flight safety.')

def source_pages():
    for start in range(0,len(SOURCES),13):
        B.new(f'Source register / {start//13+1}','Primary manufacturer and firmware sources checked 14 September 2026. Click a title in the PDF to open its source.')
        y=103
        for sid,title,url,note in SOURCES[start:start+13]:
            B.text(30,y,sid,9,BLUE,True);B.text(80,y,title,10,BLUE,True)
            if url.startswith('http'):B.c.linkURL(url,(80,H-y-3,810,H-y+12),relative=0,thickness=0)
            B.text(80,y+15,note,8.7,MUTED)
            y+=33
        B.footer('Project-selected assignments, calculations and circuit additions are identified in the sheets. Vendor drawings retain their source attribution.')

def photo_page():
    B.new('Reference locator / actual Kakute v1.5 pads','Manufacturer overview shown for board recognition; the schematic sheets define this project connection assignment.')
    B.image(ASSETS/'kakute-h7-v1.5.jpg',30,93,571,427)
    B.box(623,98,189,117,'CHECK THE LABEL','Board must be Kakute H7 v1.5, full-size. The Mini and V2 are different boards. USB and ESC1 connector locations identify this drawing view.',BLUE)
    B.box(623,232,189,133,'PROJECT USE','R3/T3: RP1\nR4/T4: GNSS\nSDA/SCL: compass\nZ-: Finder BZ\n5V/G: accessories\nESC1: matched stack cable',GREEN)
    B.box(623,382,189,132,'VERIFY SILKSCREEN','Some public documents list older sensor and power specifications. Use received revision, current manufacturer drawing and actual firmware detection together.',ORANGE)
    B.footer('Figure reproduced from Holybro current Kakute H7 v1.5 diagram (S30); its promotional text is not a tested performance claim for this build.')

def save_companion():
    (OUT/'connection-netlist.json').write_text(json.dumps({'revision':'A','date':'2026-09-14','baseline':'PalmPilot_BOM.pdf 34 pages','connections':WIRES},indent=2))
    bom_link = Path(os.path.relpath(ROOT/'docs/reference/PalmPilot_BOM.pdf', OUT)).as_posix()
    lines=['# PalmPilot / Manta Flow - connection list, Rev A','',f'Baseline: [PalmPilot_BOM.pdf]({bom_link}), 14 September 2026. Use with the [PDF schematic](PalmPilot_Full_Schematic_and_Build_Guide.pdf).','',
      '**Trainer is a bench prototype:** the exact Pocket input tolerance and dropout behavior require validation before connecting/enabling it. All power domains are independent; only hub and Pocket share trainer ground.','',
      'Connection count includes local component leads, factory battery leads, and the separate twelve motor phase leads. A shared net requires a real soldered junction.','',
      '| ID | Net | From | To | Wire | Note |','|---|---|---|---|---|---|']
    for w in WIRES:lines.append('| '+' | '.join(w[k].replace('|','/') for k in ['id','net','source','destination','wire','notes'])+' |')
    lines += ['','## Sources','']
    for sid,title,url,note in SOURCES:
        if url.startswith('local: '):
            relative = Path(os.path.relpath(ROOT/url[7:], OUT)).as_posix()
            lines.append(f'- **{sid}:** [{title}](<{relative}>) - {note}')
        else:lines.append(f'- **{sid}:** [{title}]({url}) - {note}')
    (OUT/'connection-list.md').write_text('\n'.join(lines)+'\n')
    (OUT/'render-manifest.json').write_text(json.dumps(B.pages,indent=2))

if __name__=='__main__':
    OUT = ARGS.output_dir.expanduser().resolve()
    SVG = OUT/'schematic-sheets'
    PDF = OUT/'PalmPilot_Full_Schematic_and_Build_Guide.pdf'
    SVG.mkdir(parents=True, exist_ok=True)
    register_fonts()
    B = Book()
    intro();baseline();aircraft_power();peripheral_page();aircraft_schedule()
    connectors();motor_page();connector_details();photo_page()
    hand_page('L','U6');hand_page('R','U7');wearable_power();button_page();hand_schedule();adc_notes()
    trainer_page();trainer_schedule();carrier_page();timing_page();trainer_validation()
    firmware_page();power_budget();additions_page();nc_page();assembly_page();acceptance_page();source_pages()
    B.save();save_companion()
    print(f'Created {PDF} ({B.page} pages, {len(WIRES)} connection records)')
