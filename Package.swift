// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "Symphony",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "symphony", targets: ["Symphony"]),
    ],
    targets: [
        .executableTarget(
            name: "Symphony",
            path: "Sources/Symphony"
        ),
    ]
)
