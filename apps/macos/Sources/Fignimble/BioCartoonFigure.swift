import AppKit

// BioCartoon.swift and BioCartoonLibrary.swift are Manimble's, unchanged but for names; this file joins them to
// Fignimble's window: the search takes the inspector's place, and an icon goes into images/ and on the figure.

/// Where Fignimble keeps its own files (its Python environment, BioCartoon's offline pictures when the editor has none).
enum Workspace {
    static var base: URL {
        let u = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("Fignimble")
        try? FileManager.default.createDirectory(at: u, withIntermediateDirectories: true)
        return u
    }
}

/// Reading and writing pictures, for BioCartoon's files.
enum ImageExtractor {
    enum Failure: Error { case unreadable }
    static func load(path: String) throws -> CGImage {
        guard let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
              let cg = CGImageSourceCreateImageAtIndex(src, 0, [kCGImageSourceShouldCache: false] as CFDictionary) else {
            throw Failure.unreadable
        }
        return cg
    }
    static func png(_ image: CGImage) -> Data? {
        NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:])
    }
}

extension MainController {
    /// Insert ▸ BioCartoon Icons… (and the toolbar button): the search takes the inspector's place; again puts it away.
    @objc func showBioCartoon(_ sender: Any?) {
        if let p = biocartoonPane, !p.view.isHidden { hideBioCartoon(); return }
        let p = biocartoonPane ?? BioCartoonPane()
        if biocartoonPane == nil {
            p.onInsert = { [weak self] icon in self?.insertBioCartoon(icon, at: nil) }
            p.onClose = { [weak self] in self?.hideBioCartoon() }
            p.view.translatesAutoresizingMaskIntoConstraints = false
            rightHost.addSubview(p.view)
            NSLayoutConstraint.activate([
                p.view.leadingAnchor.constraint(equalTo: rightHost.leadingAnchor), p.view.trailingAnchor.constraint(equalTo: rightHost.trailingAnchor),
                p.view.topAnchor.constraint(equalTo: rightHost.topAnchor), p.view.bottomAnchor.constraint(equalTo: rightHost.bottomAnchor),
            ])
            biocartoonPane = p
        }
        p.view.isHidden = false
        inspector.isHidden = true
        if rightHost.isHidden { rightHost.isHidden = false }
        p.activate(in: window)
    }

    /// Back to the inspector.
    func hideBioCartoon() {
        BCInfoTip.shared.hide()
        biocartoonPane?.view.isHidden = true
        inspector.isHidden = false
    }

    /// An icon dragged from the search onto the canvas (`p` in mm).
    func biocartoonDropped(_ data: Data, at p: CGPoint) -> Bool {
        guard figure != nil, let icon = try? JSONDecoder().decode(BCIcon.self, from: data) else { return false }
        insertBioCartoon(icon, at: p)
        return true
    }

    /// Download the icon into the project's images/ folder (SVG when it is published as one, else PNG) and place it
    /// centred on `point` (mm; nil = the figure's centre), 25 mm on its longer side, with no panel letter.
    func insertBioCartoon(_ icon: BCIcon, at point: CGPoint?) {
        guard let project, let f = figure, let exe = biocartoonPane?.exe else { return }
        let images = URL(fileURLWithPath: project).appendingPathComponent("images")
        try? FileManager.default.createDirectory(at: images, withIntermediateDirectories: true)
        let slug = icon.title.lowercased().components(separatedBy: CharacterSet.alphanumerics.inverted).filter { !$0.isEmpty }
            .prefix(6).joined(separator: "_")
        let stem = slug.isEmpty ? "biocartoon" : slug
        var base = stem, n = 1
        while ["png", "svg"].contains(where: { FileManager.default.fileExists(atPath: images.appendingPathComponent("\(base).\($0)").path) }) {
            base = "\(stem)_\(n)"; n += 1
        }
        let png = images.appendingPathComponent(base + ".png"), svg = images.appendingPathComponent(base + ".svg")
        let c = point ?? CGPoint(x: f.size.width / 2, y: f.size.height / 2)
        busyPill.show("Downloading \(icon.title)…", symbol: nil, tint: nil, spinning: true, cancellable: false)
        Task { @MainActor in
            var size = CGSize(width: icon.width ?? 1, height: icon.height ?? 1)
            var dest = png
            do {
                // PyMuPDF draws SVG itself, so a vector icon goes in as it is published
                if icon.svg_key != nil, (try? await BioCartoonCLI.fetchSVG(exe, id: icon.id, to: svg)) != nil {
                    BioCartoonCLI.tagSVG(svg, with: icon)
                    dest = svg
                } else {
                    // the downloaded PNG when there is one (no internet needed), else the catalog's
                    if !(await Task.detached { BCOffline.copy(icon, to: png, maxSide: 1600) }.value) {
                        try await BioCartoonCLI.fetch(exe, id: icon.id, to: png)
                    }
                    size = await Task.detached { () -> CGSize in
                        let s = BioCartoonCLI.trimTransparentMargins(png)
                        BioCartoonCLI.tag(png, with: icon)
                        return s
                    }.value
                }
            } catch { busyPill.hide(); toast("Could not download \(icon.title): \(error)", error: true); return }
            busyPill.hide()
            BCDownloads.add(icon)
            let aspect = size.width > 0 && size.height > 0 ? Double(size.height / size.width) : 1
            let w = aspect > 1 ? 25 / aspect : 25, h = w * aspect
            placePicture(dest.path, x: Double(c.x) - w / 2, y: Double(c.y) - h / 2, w: w, lettered: false)
        }
    }

    /// The right-click menu's BioCartoon items for the selected picture: its credit when it came from the catalog,
    /// otherwise Add to Local / Upload to Online BioCartoon Library (as the BioCartoon editor's canvas menu).
    func bioCartoonMenuItems() -> [NSMenuItem] {
        guard let project, canvas.selection.count == 1, let e = figure?.element(canvas.selection[0]), e.kind == "image",
              let src = e.props["source"] as? String else { return [] }
        let path = src.hasPrefix("/") ? src : URL(fileURLWithPath: project).appendingPathComponent(src).path
        guard FileManager.default.fileExists(atPath: path) else { return [] }
        if let icon = BioCartoonCLI.origin(ofImageAt: path) {
            return [BCMenuItem("Show BioCartoon Credit…") { [weak self] in self?.showBioCartoonCredit(icon) }]
        }
        return bioCartoonLibraryItems(path)
    }

    /// Right-click ▸ Show BioCartoon Credit…: who made the artwork, ready to copy into the legend.
    func showBioCartoonCredit(_ icon: BCIcon) {
        let a = NSAlert()
        a.messageText = icon.title
        a.informativeText = icon.credit ?? icon.title
        a.icon = BioCartoonCLI.logo
        a.addButton(withTitle: "Copy Credit")
        a.addButton(withTitle: "Done")
        a.beginSheetModal(for: window) { [weak self] r in
            guard r == .alertFirstButtonReturn else { return }
            BioCartoonCLI.copy(icon.credit ?? icon.title)
            self?.toast("Copied the credit")
        }
    }
}
