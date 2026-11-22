from __future__ import annotations

import html
import struct
import zlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "GeoSentinelAI_Project_Overview.pptx"
W, H = 12192000, 6858000
BG, INK, MUTED = "F3F2EB", "172522", "63716B"
GREEN, LIME, ORANGE, WHITE = "315E4A", "C5D96B", "E58D55", "FFFFFF"
FONT = "Aptos"

def esc(s):
    return html.escape(str(s), quote=False)

def emu(x, y, w, h):
    return tuple(int(v * 914400) for v in (x, y, w, h))

class Slide:
    def __init__(self, bg=BG):
        self.items = []
        self.rels = []
        self.bg = bg
        self.idx = 2

    def shape(self, x, y, w, h, fill, radius=False, line=None):
        x, y, w, h = emu(x,y,w,h)
        geom = 'roundRect' if radius else 'rect'
        stroke = f'<a:ln w="12700"><a:solidFill><a:srgbClr val="{line}"/></a:solidFill></a:ln>' if line else '<a:ln><a:noFill/></a:ln>'
        self.items.append(f'<p:sp><p:nvSpPr><p:cNvPr id="{self.idx}" name="Shape {self.idx}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm><a:prstGeom prst="{geom}"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>{stroke}</p:spPr></p:sp>')
        self.idx += 1

    def text(self, x, y, w, h, text, size=16, color=INK, bold=False, font=FONT, align='l', valign='ctr', margin=0.04, italic=False):
        x,y,w,h=emu(x,y,w,h)
        paras=[]
        for line in str(text).split('\n'):
            run=f'<a:r><a:rPr lang="en-US" sz="{int(size*100)}" b="{1 if bold else 0}" i="{1 if italic else 0}"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill><a:latin typeface="{font}"/></a:rPr><a:t>{esc(line)}</a:t></a:r>'
            paras.append(f'<a:p><a:pPr algn="{align}"/><a:lnSpc><a:spcPct val="112000"/></a:lnSpc>{run}<a:endParaRPr lang="en-US" sz="{int(size*100)}"/></a:p>')
        m=int(margin*914400)
        self.items.append(f'<p:sp><p:nvSpPr><p:cNvPr id="{self.idx}" name="Text {self.idx}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln></p:spPr><p:txBody><a:bodyPr wrap="square" anchor="{valign}" lIns="{m}" rIns="{m}" tIns="{m}" bIns="{m}"/><a:lstStyle/>{"".join(paras)}</p:txBody></p:sp>')
        self.idx += 1

    def image(self, path, x, y, w, h, idx):
        name=f'image{idx}.jpg'
        relid=f'rId{len(self.rels)+2}'
        self.rels.append((relid, f'../media/{name}'))
        x,y,w,h=emu(x,y,w,h)
        self.items.append(f'<p:pic><p:nvPicPr><p:cNvPr id="{self.idx}" name="{name}"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="{relid}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm><a:prstGeom prst="roundRect"><a:avLst/></a:prstGeom></p:spPr></p:pic>')
        self.idx += 1

    def xml(self):
        xfrm='<a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></a:xfrm>'
        tree=f'<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr>{xfrm}</p:grpSpPr>{"".join(self.items)}</p:spTree>'
        return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="{self.bg}"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>{tree}</p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'

def base_slide(n, label):
    s=Slide()
    s.text(.62,.35,7,.28,'GEOSENTINEL  /  FIELD INTELLIGENCE',9,GREEN,True,font='Aptos Mono')
    s.text(10.5,.34,2.2,.28,f'PROJECT BRIEF   /   {n:02d}',8,MUTED,True,font='Aptos Mono',align='r')
    s.shape(.62,.77,12.05,.012,'D6D9CE')
    s.text(.62,7.22,7,.22,label,8,MUTED,font='Aptos Mono')
    s.text(12.05,7.18,.55,.25,f'{n:02d}',9,GREEN,True,font='Aptos Mono',align='r')
    return s

def build():
    slides=[]
    # 1: cover
    s=Slide(INK)
    s.text(.72,.56,6,.35,'GEOSENTINEL  /  FIELD INTELLIGENCE',10,LIME,True,font='Aptos Mono')
    s.shape(.72,1.45,.09,.92,LIME,True)
    s.text(1.02,1.25,7.7,1.55,'See the change.\nInvestigate with evidence.',34,WHITE,True)
    s.text(1.05,3.12,6.6,.8,'Satellite change monitoring for quarry expansion\nand land-use review.',17,'D6DED4')
    s.shape(1.05,4.42,2.45,.48,GREEN,True)
    s.text(1.16,4.46,2.25,.36,'PUNE REGION  /  MVP',10,LIME,True,font='Aptos Mono',align='ctr')
    s.shape(8.7,1.26,3.65,4.6,'263530',True)
    # stylized satellite scan visualization
    for i in range(6): s.shape(9.0+i*.5,1.62,.025,3.8,'45584B')
    for i in range(8): s.shape(8.95,1.75+i*.47,3.1,.018,'45584B')
    s.shape(9.32,2.28,1.15,.78,'55775A',True)
    s.shape(10.62,2.12,1.18,1.02,'91754C',True)
    s.shape(9.55,3.32,1.47,.92,'7C664A',True)
    s.shape(11.15,3.48,.65,.68,ORANGE,True)
    s.shape(10.55,4.62,1.1,.1,LIME,True)
    s.shape(10.48,4.56,.12,.24,LIME,True)
    s.text(9.03,5.25,2.9,.3,'CHANGE SIGNAL  /  REVIEW',9,LIME,True,font='Aptos Mono')
    s.text(.73,7.18,7,.22,'PRODUCT OVERVIEW  •  ENGINEERING MVP',8,'B1BDB3',font='Aptos Mono')
    slides.append(s)
    # 2 problem and product
    s=base_slide(2,'01  /  THE OPPORTUNITY')
    s.text(.7,1.05,6.2,.75,'Land change is easy to miss\nbetween site visits.',24,INK,True)
    s.text(.72,2.2,5.0,.95,'Satellite scenes capture a wider view, but turning pixels into a reviewable case takes time and context.',15,MUTED)
    s.shape(6.55,1.1,5.98,4.92,INK,True)
    s.text(6.92,1.5,5.2,.35,'GEOSENTINEL AI',11,LIME,True,font='Aptos Mono')
    s.text(6.92,2.02,4.95,1.1,'A repeatable path from imagery to investigation.',25,WHITE,True)
    s.text(6.92,3.38,4.85,1.12,'Compare scenes, flag candidate change, map findings, and package evidence for human review.',16,'DCE2D7')
    for j,(num,txt) in enumerate([('01','ACQUIRE'),('02','COMPARE'),('03','REVIEW')]):
        x=6.94+j*1.78
        s.shape(x,5.03,1.5,.54,'315E4A',True)
        s.text(x+.08,5.09,1.34,.4,f'{num}  {txt}',9,LIME,True,font='Aptos Mono',align='ctr')
    s.text(.75,4.0,4.8,.3,'BUILT FOR',10,GREEN,True,font='Aptos Mono')
    s.text(.75,4.43,4.95,1.0,'Environmental and mining consultants\nLand and infrastructure operators',16,INK)
    slides.append(s)
    # 3 workflow
    s=base_slide(3,'02  /  FROM SCENE TO SIGNAL')
    s.text(.7,1.0,10.4,.55,'A transparent, multi-step change workflow',25,INK,True)
    steps=[('01','Find scenes','Sentinel-2 L2A\nPune area · cloud filter'),('02','Prepare','10 m bands · align\nmask clouds & shadows'),('03','Compare','NDVI + BSI signals\noptional CNN score'),('04','Extract','Connected components\narea & coordinates'),('05','Review','Map · timeline\ncase-file report')]
    for i,(n,t,d) in enumerate(steps):
        x=.72+i*2.48
        s.shape(x,2.15,2.16,3.05,WHITE,True,line='D8DDD3')
        s.text(x+.2,2.42,.6,.35,n,12,GREEN,True,font='Aptos Mono')
        s.text(x+.2,3.02,1.8,.55,t,18,INK,True)
        s.text(x+.2,3.85,1.8,.8,d,12,MUTED)
        if i<4:
            s.shape(x+2.22,3.47,.19,.035,GREEN)
    s.shape(.72,5.7,11.84,.68,'E8E9DF',True)
    s.text(.95,5.86,11.4,.35,'TEN-MINUTE DASHBOARD REFRESH   ≠   SATELLITE REVISIT   /   SCENE AVAILABILITY DEPENDS ON ACQUISITION',10,GREEN,True,font='Aptos Mono',align='ctr')
    slides.append(s)
    # 4 architecture
    s=base_slide(4,'03  /  SYSTEM ARCHITECTURE')
    s.text(.7,1.03,10,.5,'A small stack with a clear data path',24,INK,True)
    nodes=[(.8,2.0,2.25,1.08,'NEXT.JS DASHBOARD','Map · timeline · reports'),(4.0,2.0,2.25,1.08,'FASTAPI SERVICE','Acquisition · analysis'),(7.15,1.45,2.15,1.05,'PLANETARY COMPUTER','STAC · Sentinel-2 COGs'),(7.15,3.0,2.15,1.05,'ANALYSIS PIPELINE','Raster · indices · CNN'),(10.1,2.0,2.15,1.08,'STORAGE','Neo4j + CSV fallback')]
    for x,y,w,h,t,d in nodes:
        s.shape(x,y,w,h,WHITE,True,line='D5DAD0')
        s.text(x+.15,y+.16,w-.3,.26,t,10,GREEN,True,font='Aptos Mono')
        s.text(x+.15,y+.52,w-.3,.36,d,12,INK)
    # connectors as lines
    for x,y,w,h in [(3.05,2.52,.78,.025),(6.25,2.52,.75,.025),(9.3,2.03,.8,.025),(9.3,3.52,.8,.025)]:s.shape(x,y,w,h,GREEN)
    s.text(.85,4.55,5.3,.3,'BROWSER SERVICES',10,GREEN,True,font='Aptos Mono')
    s.text(.85,4.96,5.4,.75,'OpenStreetMap tiles · Nominatim reverse geocoding\nGoogle Maps links from each finding',13,MUTED)
    s.shape(6.85,4.55,5.38,1.22,'E9EADD',True)
    s.text(7.12,4.78,4.95,.26,'RESILIENCE',10,GREEN,True,font='Aptos Mono')
    s.text(7.12,5.15,4.88,.45,'Cached real feed when provider limits access; CSV when graph storage is unavailable.',12,INK)
    slides.append(s)
    # 5 live dashboard screenshot
    s=base_slide(5,'04  /  OPERATOR EXPERIENCE')
    s.text(.7,1.0,9,.5,'One workspace for scan context and findings',24,INK,True)
    pic=ROOT/'docs'/'img'/'Screenshot 2026-11-02 211619.png'
    s.shape(.72,1.78,8.1,4.62,INK,True)
    s.image(pic, .82,1.88,7.9,4.42,1)
    s.text(9.2,1.95,3.0,.32,'DASHBOARD',10,GREEN,True,font='Aptos Mono')
    s.text(9.2,2.4,3.0,1.0,'Live or cached imagery, clearly labeled.',20,INK,True)
    s.text(9.2,3.65,2.8,1.5,'• Scene comparison\n• Finding map\n• Temporal timeline\n• Downloadable case file',13,MUTED)
    s.shape(9.15,5.52,3.1,.7,'E8E9DF',True)
    s.text(9.3,5.66,2.75,.4,'REVIEW STATUS  /  NEEDS REVIEW',9,GREEN,True,font='Aptos Mono',align='ctr')
    slides.append(s)
    # 6 evidence & boundaries
    s=base_slide(6,'05  /  EVIDENCE & INTERPRETATION')
    s.text(.7,1.0,10.7,.62,'A change signal is a starting point for investigation.',23,INK,True)
    s.text(.74,1.84,5.3,.85,'Each candidate includes location, estimated changed area, severity, confidence, observation dates, and map links.',15,MUTED)
    s.shape(.75,3.05,5.55,2.42,WHITE,True,line='D8DDD3')
    s.text(1.02,3.32,4.95,.28,'EVIDENCE PACKAGE',10,GREEN,True,font='Aptos Mono')
    s.text(1.02,3.8,4.9,1.25,'Scene dates + source\nGeoreferenced finding\nEstimated area & uncertainty\nJSON case report',14,INK)
    s.shape(6.78,1.95,5.45,3.52,'F2E7D9',True)
    s.text(7.1,2.27,4.8,.3,'INTERPRETATION LIMITS',10,'9B542E',True,font='Aptos Mono')
    s.text(7.1,2.8,4.7,1.85,'• Weak labels are not expert validation.\n• Candidate change can have other causes.\n• Not legal proof or an automatic enforcement decision.\n• Verify on the ground before action.',14,INK)
    s.text(.8,6.05,11.3,.35,'DESIGNED FOR HUMAN REVIEW  /  NO AUTOMATIC CONCLUSION ABOUT ILLEGAL ACTIVITY',10,GREEN,True,font='Aptos Mono',align='ctr')
    slides.append(s)
    # 7 implementation
    s=base_slide(7,'06  /  WHAT EXISTS TODAY')
    s.text(.7,1.0,10.8,.55,'A working prototype with a focused next step',24,INK,True)
    cards=[('ACQUISITION','Sentinel-2 L2A scene search\nUp to 8 low-cloud scenes\n10 m spectral bands'),('ANALYSIS','Cloud masking + alignment\nNDVI / BSI change signals\nOptional ChangeCNN score'),('PRODUCT','Next.js dashboard\nFastAPI endpoints\nNeo4j with CSV fallback'),('NEXT MILESTONE','Expert-labeled examples\nEvaluate false positives\nExpand beyond Pune')]
    for i,(title,body) in enumerate(cards):
        x=.74+(i%2)*5.95;y=1.95+(i//2)*2.0
        s.shape(x,y,5.5,1.52,WHITE,True,line='D8DDD3')
        s.text(x+.22,y+.18,5.0,.3,title,10,GREEN,True,font='Aptos Mono')
        s.text(x+.22,y+.58,5.0,.72,body,13,INK)
    s.text(.85,6.32,11.4,.35,'CURRENT SCOPE: STATIC PUNE MONITORING REGION  /  AUTHENTICATION IS NOT CONNECTED IN THIS MVP',9,MUTED,True,font='Aptos Mono',align='ctr')
    slides.append(s)
    # 8 close
    s=Slide(INK)
    s.text(.72,.56,6,.35,'GEOSENTINEL  /  FIELD INTELLIGENCE',10,LIME,True,font='Aptos Mono')
    s.shape(.72,1.4,.09,.88,LIME,True)
    s.text(1.02,1.24,9.2,.9,'From pixels to a reviewable case.',30,WHITE,True)
    s.text(1.05,2.58,8.5,.72,'Acquire. Compare. Map. Verify.',20,'DCE2D7')
    s.shape(1.05,4.0,4.4,1.05,'263530',True)
    s.text(1.32,4.18,3.9,.62,'GeoSentinel AI\nSatellite change monitoring · Pune MVP',12,LIME,True,font='Aptos Mono')
    s.text(1.05,6.85,8,.28,'CANDIDATE SIGNALS REQUIRE FIELD VERIFICATION',9,'B1BDB3',True,font='Aptos Mono')
    slides.append(s)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    media=[]
    for i,src in enumerate([ROOT/'docs'/'img'/'Screenshot 2026-11-02 211619.png'],1):
        im=Image.open(src).convert('RGB')
        # resize large screenshots to a clear, compact deck asset
        im.thumbnail((1800,1100), Image.Resampling.LANCZOS)
        dst=OUT.parent/f'._deck_image_{i}.jpg'
        im.save(dst,quality=88,optimize=True)
        media.append((f'ppt/media/image{i}.jpg',dst))
    content_types=['<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>','<Default Extension="xml" ContentType="application/xml"/>','<Default Extension="jpg" ContentType="image/jpeg"/>','<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>','<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>','<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>']
    for i in range(1,len(slides)+1): content_types.append(f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>')
    with ZipFile(OUT,'w',ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',f'<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">{"".join(content_types)}</Types>')
        z.writestr('_rels/.rels','''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/></Relationships>''')
        ids=''.join(f'<p:sldId id="{255+i}" r:id="rId{i+1}"/>' for i in range(len(slides)))
        z.writestr('ppt/presentation.xml',f'''<?xml version="1.0" encoding="UTF-8"?><p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst><p:sldIdLst>{ids}</p:sldIdLst><p:sldSz cx="{W}" cy="{H}" type="wide"/><p:notesSz cx="6858000" cy="9144000"/><p:defaultTextStyle><p:lvl1pPr marL="0" indent="0"><a:defRPr sz="1800"/></p:lvl1pPr></p:defaultTextStyle></p:presentation>''')
        rels='<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'+''.join(f'<Relationship Id="rId{i+2}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i+1}.xml"/>' for i in range(len(slides)))
        z.writestr('ppt/_rels/presentation.xml.rels',f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>')
        z.writestr('ppt/slideMasters/slideMaster1.xml','''<?xml version="1.0" encoding="UTF-8"?><p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld><p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/><p:sldLayoutIdLst><p:sldLayoutId id="1" r:id="rId1"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>''')
        z.writestr('ppt/slideMasters/_rels/slideMaster1.xml.rels','''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/></Relationships>''')
        z.writestr('ppt/slideLayouts/slideLayout1.xml','''<?xml version="1.0" encoding="UTF-8"?><p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1"><p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>''')
        z.writestr('ppt/slideLayouts/_rels/slideLayout1.xml.rels','''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>''')
        for i,slide in enumerate(slides,1):
            z.writestr(f'ppt/slides/slide{i}.xml',slide.xml())
            rels=f'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
            for rid,target in slide.rels: rels+=f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="{target}"/>'
            z.writestr(f'ppt/slides/_rels/slide{i}.xml.rels',f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>')
        for path,dst in media: z.write(dst,path)
    for _,dst in media: dst.unlink(missing_ok=True)
    print(f'Created {OUT} ({OUT.stat().st_size:,} bytes, {len(slides)} slides)')

if __name__=='__main__': build()
