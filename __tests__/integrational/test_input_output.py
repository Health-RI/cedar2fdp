import difflib

from colorama import Fore


def color_diff(line):
    if line.startswith("+"):
        return Fore.YELLOW + line + Fore.RESET
    elif line.startswith("-"):
        return Fore.RED + line + Fore.RESET
    else:
        return line


def compare_files():
    with open("../../example-output/2023-05-26_output_latest.ttl", "r") as file_1:
        file_1_text = file_1.readlines()

    with open("../../example-output/2023-05-26_output.ttl", "r") as file_2:
        file_2_text = file_2.readlines()

    diff = difflib.unified_diff(
        file_1_text,
        file_2_text,
        fromfile="file1.txt",
        tofile="file2.txt",
        n=1,
        lineterm="",
    )
    files_different = False
    if diff:
        files_different = True
        for line in diff:
            print(color_diff(line))
    return files_different


if __name__ == "__main__":
    print(compare_files())
