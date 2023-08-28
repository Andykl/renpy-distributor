## Ren'Py Distributor
This project aims to improve the building of Ren'Py projects, especially large projects.
The main objectives of this project are:
1. Make the build process faster.
2. Make the build process more informative, especially if something has gone wrong.
3. Add a more user-friendly CLI and GUI interfaces.
4. Have the ability to run the build process via GitHub Actions.
5. Have an easier way to customize archives and formats for advanced users.

## Installation

1. Clone or download this repository to your local machine.
2. Navigate to the root directory of the downloaded repository.

## Usage

This tool serves as a distributor for RenPy games. It provides functionalities for building and distributing RenPy games efficiently.

### Prerequisites

Before using this tool, ensure you have the following prerequisites installed:

- Python (version should match python used in SDK)
- RenPy SDK (8.0 or higher)

### Command Line Interface

The tool offers a command-line interface (CLI) for various tasks related to building and distributing RenPy games.

#### Build Command

The primary command is `build`, which allows you to build the game. Here's the basic syntax:

```bash
python renpy_distributor.py build --project-dir PROJECT_DIR --sdk-dir SDK_DIR [options] [build_packages...]

optional arguments:
  --tmp-dir TMP_DIR     Path to the tmp directory.If ommitted, defaults to SDK-DIR/tmp.
  --log-file LOG_FILE   The name of the log file to write build progress.
                        If ommitted, only prints to the console.
  --legacy-build        Compiles the game to retrieve dump with build info.
                        If ommitted, buildinfo.toml file in PROJECT-DIR is expected to exist.
  --silent              Prints only error or success messages to the console
                        (but the log output remains unchanged).
  --verbose             Prints a more verbous output in the console and log.
```

# License
This project is distributed under the MIT Licence and also contains files belonging to
Ren'Py originating from https://github.com/renpy/renpy and https://github.com/renpy/renpy-build.
