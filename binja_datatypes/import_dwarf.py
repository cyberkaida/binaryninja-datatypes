#!/usr/bin/env python3

from functools import cache, cached_property
from pathlib import Path
from typing import Optional

import logging
from logging import Logger

logging.basicConfig(level=logging.DEBUG)
base_logger = logging.getLogger("binaryninja-dwarf")


try:
    import binaryninja
except ImportError:
    print("BinaryNinja could not be imported.")
    print("Please check you have installed BinaryNinja into this python environment.")
    print("Or you are running this inside of BinaryNinja.")
    raise

import binaryninja
from binaryninja.binaryview import BinaryView
from binaryninja.debuginfo import DebugInfoParser

class DwarfImporter:
    base_file: Path
    dwarf_file: Path
    type_archive: Path
    logger: Logger


    @cached_property
    def base_binaryview(self) -> BinaryView:
        return binaryninja.load(
            str(self.base_file),
            options={
                "corePlugins.dwarfImport": True,
            }
        )

    def __init__(self, base_file: Optional[Path] = None, dwarf_file: Optional[Path] = None, type_archive: Optional[Path] = None):
        if base_file:
            self.base_file = base_file
        else:
            self.base_file = Path(bv.file.filename) # If we do not have a base file, get the current one!

        if not self.base_file:
            raise ValueError("No base file provided and no file open in BinaryNinja")
        self.logger = base_logger.getChild(f"DwarfImporter[{self.base_file.name}]")

        self.dwarf_file = dwarf_file or self._find_dwarf_file(self.base_file)
        self.type_archive = type_archive or self.base_file.with_suffix(".bntl")

    def _find_dwarf_file(self, base_file: Path) -> Path:
        dsym_path = Path(f"{base_file}.dSYM")
        self.logger.debug(f"Looking for DWARF file for {base_file} @ {dsym_path}")
        if dsym_path.exists():
            return dsym_path / "Contents" / "Resources" / "DWARF" / base_file.name
        # TODO: Try symbol servers
        # https://ubuntu.com/server/docs/about-debuginfod

        raise FileNotFoundError(f"Could not find DWARF file for {base_file}")

    @cache
    def import_debug_info(self):
        debug_binaryview = binaryninja.load(
            str(self.dwarf_file),
        )
        debug_info = DebugInfoParser["DWARF"].parse_debug_info(self.base_binaryview, debug_binaryview)
        self.base_binaryview.apply_debug_info(debug_info)
        self.base_binaryview.update_analysis_and_wait()

    def export_type_library(self, output_file: Optional[Path] = None):
        self.import_debug_info()

        arch = self.base_binaryview.arch
        filename = Path(self.base_binaryview.file.filename).name
        name = f"{filename}_{arch}_types"
        assert arch
        assert self.base_binaryview.platform
        type_library = binaryninja.TypeLibrary.new(arch, name)
        type_library.add_platform(self.base_binaryview.platform)
        type_library.add_alternate_name(filename)

        # Now copy over the types
        for name, type in self.base_binaryview.types.items():
            self.logger.debug(f"Adding type {name} to type library")
            type_library.add_named_type(name, type)

        # And the function signatures
        for function in self.base_binaryview.functions:
            self.logger.debug(f"Adding function {function.name} to type library")
            type_library.add_named_object(function.name, function.type)

        assert type_library.finalize()

        # Now save the type library
        output_path = output_file or self.type_archive
        type_library.write_to_file(str(output_path))


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Create a BinaryNinja type archive from a DWARF file.")
    parser.add_argument("BASE_FILE", type=Path, help="The base file to to symbolicate.")
    parser.add_argument("--dwarf-file", required=False, type=Path, help="The DWARF file to import.")
    parser.add_argument("--type-library", required=False, type=Path, help="The output file to write the type archive to.")

    args = parser.parse_args()


    if args.type_library and args.type_library.suffix != ".bntl":
        parser.error("TYPE_ARCHIVE must have a .bntl extension.")

    importer = DwarfImporter(args.BASE_FILE, args.dwarf_file, args.type_library)
    importer.export_type_library()
