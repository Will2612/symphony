import Foundation

let version = "0.0.0-dev"
let swiftVersion = "6.3.2"

let argv = CommandLine.arguments
let exeName = (argv.first as NSString?)?.lastPathComponent ?? "symphony"

func printVersion() {
    print("symphony \(version) (swift \(swiftVersion))")
}

func printHelp() {
    let usage = """
    Usage: \(exeName) [option]

      --version, -v    Print version and exit
      --help, -h       Print this help and exit

    Symphony Swift daemon. See SPEC.md and Plan.md.
    """
    print(usage)
}

guard argv.count >= 2 else {
    FileHandle.standardError.write(Data("error: missing required option. Run `\(exeName) --help`.\n".utf8))
    exit(64)
}

switch argv[1] {
case "--version", "-v":
    printVersion()
case "--help", "-h":
    printHelp()
default:
    FileHandle.standardError.write(Data("error: unknown option `\(argv[1])`. Run `\(exeName) --help`.\n".utf8))
    exit(64)
}
