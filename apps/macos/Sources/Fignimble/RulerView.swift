import AppKit

/// A ruler in millimeters along the top or left of the canvas, 0 at the figure's top-left corner, following the
/// canvas's zoom and pan. It shows the figure's extent, the selection's and the cursor; drag from it onto the
/// figure to add a guide. (After Manimble's RulerView.)
final class RulerView: NSView {
    let horizontal: Bool
    weak var canvas: CanvasView?
    var cursor: CGPoint? { didSet { needsDisplay = true } }
    static let thickness: CGFloat = 20

    init(horizontal: Bool) {
        self.horizontal = horizontal
        super.init(frame: .zero)
        clipsToBounds = true
        toolTip = horizontal ? "Drag down onto the figure to add a horizontal guide" : "Drag right onto the figure to add a vertical guide"
    }
    required init?(coder: NSCoder) { fatalError() }
    override var isFlipped: Bool { true }

    /// A figure coordinate (mm) along this ruler, in this view's points.
    private func pos(_ v: Double) -> CGFloat {
        guard let c = canvas else { return 0 }
        let p = c.convert(c.toView(CGPoint(x: v, y: v)), to: self)
        return horizontal ? p.x : p.y
    }

    override func draw(_ dirty: NSRect) {
        Theme.barBackground.setFill(); bounds.fill()
        NSColor.separatorColor.setFill()
        if horizontal { NSRect(x: 0, y: bounds.maxY - 1, width: bounds.width, height: 1).fill() }
        else { NSRect(x: bounds.maxX - 1, y: 0, width: 1, height: bounds.height).fill() }
        guard let c = canvas, let f = c.figure else { return }
        let length = Double(horizontal ? f.size.width : f.size.height)
        // the figure's extent
        Theme.codeBackground.setFill()
        let a = pos(0), b = pos(length)
        (horizontal ? NSRect(x: a, y: 0, width: b - a, height: bounds.height - 1) : NSRect(x: 0, y: a, width: bounds.width - 1, height: b - a)).fill()
        // the selection's extent
        let sel = c.selection.compactMap { f.element($0) }.map { c.liveBox(of: $0) }.reduce(CGRect.null) { $0.union($1) }
        if !sel.isNull {
            Theme.accentSoft.setFill()
            let s0 = pos(Double(horizontal ? sel.minX : sel.minY)), s1 = pos(Double(horizontal ? sel.maxX : sel.maxY))
            (horizontal ? NSRect(x: s0, y: 0, width: s1 - s0, height: bounds.height) : NSRect(x: 0, y: s0, width: bounds.width, height: s1 - s0)).fill()
        }
        // ticks: a labeled one at least ~40 pt apart
        let ppm = Double(c.scale)
        let major = [1.0, 2, 5, 10, 20, 50, 100].first { $0 * ppm >= 40 } ?? 200
        let minor = major / (major == 2 || major == 20 ? 4 : 5)
        let attrs: [NSAttributedString.Key: Any] = [.font: Theme.font(9), .foregroundColor: Theme.ink(0.55)]
        Theme.ink(0.35).setFill()
        let visible0 = horizontal ? Double(c.toMM(c.convert(CGPoint(x: 0, y: 0), from: self)).x) : Double(c.toMM(c.convert(CGPoint(x: 0, y: 0), from: self)).y)
        var v = (visible0 / minor).rounded(.down) * minor
        let thick = horizontal ? bounds.height : bounds.width
        while true {
            let p = pos(v)
            if p > (horizontal ? bounds.width : bounds.height) { break }
            let isMajor = abs((v / major).rounded() * major - v) < 1e-6
            let len: CGFloat = isMajor ? 8 : 4
            if horizontal { NSRect(x: p.rounded(), y: thick - len, width: 1, height: len).fill() }
            else { NSRect(x: thick - len, y: p.rounded(), width: len, height: 1).fill() }
            if isMajor {
                let s = NSAttributedString(string: mm(v), attributes: attrs)
                if horizontal { s.draw(at: CGPoint(x: p + 2, y: 1)) }
                else {
                    NSGraphicsContext.saveGraphicsState()
                    let t = NSAffineTransform(); t.translateX(by: 2, yBy: p - 2); t.rotate(byDegrees: -90); t.concat()
                    s.draw(at: CGPoint(x: 0, y: 0))
                    NSGraphicsContext.restoreGraphicsState()
                }
            }
            v += minor
        }
        if let cur = cursor {
            Theme.accent.setFill()
            let p = pos(Double(horizontal ? cur.x : cur.y))
            if horizontal { NSRect(x: p, y: 0, width: 1, height: thick).fill() } else { NSRect(x: 0, y: p, width: thick, height: 1).fill() }
        }
    }

    override func mouseDown(with e: NSEvent) { canvas?.beginRulerGuide(vertical: !horizontal) }
    override func mouseDragged(with e: NSEvent) { canvas?.rulerGuideDragged(e.locationInWindow) }
    override func mouseUp(with e: NSEvent) { canvas?.rulerGuideEnded() }
}
