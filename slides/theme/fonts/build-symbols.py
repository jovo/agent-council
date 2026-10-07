"""Build theme/fonts/base-symbols.ttf: a tiny colour font (COLR/CPAL) with only
three status glyphs, so slides can type them as plain characters:

    U+25CF  ●  yes     (palette colour 0, green)
    U+25D0  ◐  partly  (palette colour 1, orange)
    U+25CB  ○  no      (palette colour 2, red)

Palette 1 is a monochrome alternative (white / grey / grey).
Run from theme/fonts:  python3 build-symbols.py   (needs: pip install fonttools)
"""
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.colorLib.builder import buildCOLR, buildCPAL

UPM=1000; CX=500; CY=330; R=400; T=80; ADV=1000
K=0.5523
def circle(pen, cx, cy, r, cw):
    k=K*r
    pts=[(cx, cy+r),(cx+r, cy),(cx, cy-r),(cx-r, cy)] if cw else [(cx, cy+r),(cx-r, cy),(cx, cy-r),(cx+r, cy)]
    pen.moveTo(pts[0])
    for i in range(4):
        a=pts[i]; b=pts[(i+1)%4]
        # control points along tangents
        ax,ay=a; bx,by=b
        def tan(p,toward):
            px,py=p; dx=px-cx; dy=py-cy
            # tangent perpendicular to radius, pointing toward next point
            tx,ty=-dy,dx
            if (toward[0]-px)*tx+(toward[1]-py)*ty<0: tx,ty=-tx,-ty
            n=(tx*tx+ty*ty)**.5; return (px+tx/n*k, py+ty/n*k)
        pen.curveTo(tan(a,b), tan(b,a), b)
    pen.closePath()
def halfdisk(pen, cx, cy, r):  # left half, clockwise: top -> down along arc on left? use: top, arc to bottom via left, close
    k=K*r
    pen.moveTo((cx, cy+r))
    pen.lineTo((cx, cy-r))
    pen.curveTo((cx-k, cy-r),(cx-r, cy-k),(cx-r, cy))
    pen.curveTo((cx-r, cy+k),(cx-k, cy+r),(cx, cy+r))
    pen.closePath()
def glyph(draw):
    tp=TTGlyphPen(None); p=Cu2QuPen(tp, 1, reverse_direction=False); draw(p); return tp.glyph()
glyphs={'.notdef':glyph(lambda p:None),'space':glyph(lambda p:None),
 'disk':glyph(lambda p:circle(p,CX,CY,R,True)),
 'ring':glyph(lambda p:(circle(p,CX,CY,R,True),circle(p,CX,CY,R-T,False))),
 'half':glyph(lambda p:(circle(p,CX,CY,R,True),circle(p,CX,CY,R-T,False),halfdisk(p,CX,CY,R-T+1))),
 'uni25CF':glyph(lambda p:circle(p,CX,CY,R,True)),
 'uni25D0':glyph(lambda p:(circle(p,CX,CY,R,True),circle(p,CX,CY,R-T,False),halfdisk(p,CX,CY,R-T+1))),
 'uni25CB':glyph(lambda p:(circle(p,CX,CY,R,True),circle(p,CX,CY,R-T,False))),
}
order=list(glyphs)
fb=FontBuilder(UPM,isTTF=True)
fb.setupGlyphOrder(order)
fb.setupCharacterMap({0x20:'space',0x25CF:'uni25CF',0x25D0:'uni25D0',0x25CB:'uni25CB'})
fb.setupGlyf(glyphs)
fb.setupHorizontalMetrics({g:(ADV if g!='.notdef' else 500,0) for g in order})
fb.setupHorizontalHeader(ascent=800,descent=-200)
fb.setupNameTable({'familyName':'Base Symbols','styleName':'Regular'})
fb.setupOS2(sTypoAscender=800,sTypoDescender=-200,usWinAscent=800,usWinDescent=200)
fb.setupPost()
# COLR: each status glyph = one layer with its palette colour
fb.font['COLR']=buildCOLR({'uni25CF':[('uni25CF',0)],'uni25D0':[('uni25D0',1)],'uni25CB':[('uni25CB',2)]})
hexrgb=lambda h:(int(h[1:3],16)/255,int(h[3:5],16)/255,int(h[5:7],16)/255,1.0)
fb.font['CPAL']=buildCPAL([[hexrgb('#56d38c'),hexrgb('#f6a83a'),hexrgb('#ef5a50')],
                           [hexrgb('#f4f7fb'),hexrgb('#a6b2c4'),hexrgb('#a6b2c4')]])
fb.save('base-symbols.ttf')
print('wrote base-symbols.ttf')
