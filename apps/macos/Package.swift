// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "Fignimble",
    platforms: [.macOS(.v13)],
    dependencies: [
        .package(url: "https://github.com/migueldeicaza/SwiftTerm", from: "1.2.0"),
    ],
    targets: [
        .executableTarget(
            name: "Fignimble",
            dependencies: [.product(name: "SwiftTerm", package: "SwiftTerm")],
            path: "Sources/Fignimble"
        ),
    ],
    swiftLanguageVersions: [.v5]
)
