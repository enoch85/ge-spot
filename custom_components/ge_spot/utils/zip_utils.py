"""Utilities for ZIP file handling."""

import logging
import zipfile
from io import BytesIO
from typing import Optional

_LOGGER = logging.getLogger(__name__)


def unzip_single_file(
    zip_bytes: bytes, expected_extension: Optional[str] = None
) -> str:
    """
    Extract single file from ZIP archive.

    Args:
        zip_bytes: ZIP file content as bytes
        expected_extension: Optional file extension to validate (e.g. '.csv')

    Returns:
        File content as string (UTF-8 decoded)

    Raises:
        ValueError: If ZIP doesn't contain exactly one file or validation fails
        zipfile.BadZipFile: If zip_bytes is not a valid ZIP file
    """
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            files = zf.namelist()

            if len(files) == 0:
                raise ValueError("ZIP archive is empty")

            if len(files) > 1:
                _LOGGER.warning(
                    f"ZIP contains {len(files)} files, expected 1. "
                    f"Will use first file: {files[0]}"
                )

            # Use first file
            csv_file = files[0]

            # Validate extension if specified
            if expected_extension and not csv_file.lower().endswith(
                expected_extension.lower()
            ):
                raise ValueError(
                    f"Expected file with extension '{expected_extension}', "
                    f"got '{csv_file}'"
                )

            _LOGGER.debug(
                f"Extracting file: {csv_file} ({zf.getinfo(csv_file).file_size} bytes)"
            )

            # Extract and decode
            with zf.open(csv_file) as f:
                content = f.read().decode("utf-8")

            _LOGGER.debug(
                f"Successfully extracted {len(content)} characters from {csv_file}"
            )
            return content

    except zipfile.BadZipFile as e:
        raise zipfile.BadZipFile(f"Invalid ZIP file: {e}")
    except UnicodeDecodeError as e:
        raise ValueError(f"Could not decode file as UTF-8: {e}")


def get_zip_info(zip_bytes: bytes) -> dict:
    """
    Get information about ZIP archive contents.

    Args:
        zip_bytes: ZIP file content as bytes

    Returns:
        Dictionary with:
        - file_count: Number of files in archive
        - files: List of file names
        - total_size: Total uncompressed size in bytes
    """
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        files = zf.namelist()
        total_size = sum(zf.getinfo(f).file_size for f in files)

        return {
            "file_count": len(files),
            "files": files,
            "total_size": total_size,
        }
