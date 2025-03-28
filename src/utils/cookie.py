import os
import shutil
import tempfile

from dotenv import load_dotenv

load_dotenv()

temp_cookie_path = None


class TemporaryCookie:
    def __init__(self):
        self.cookie_path = os.getenv("COOKIEFILE")
        self.temp_path = None

    def __enter__(self):
        if self.cookie_path and os.path.isfile(self.cookie_path):
            temp_cookie = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
            shutil.copyfile(self.cookie_path, temp_cookie.name)
            # fix_netscape_cookie_format(temp_cookie.name, temp_cookie.name)
            self.temp_path = temp_cookie.name
            return self.temp_path
        return None

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.temp_path and os.path.isfile(self.temp_path):
            try:
                os.remove(self.temp_path)
                print(f"[DEBUG] 쿠키 삭제됨: {self.temp_path}")
            except Exception as e:
                print(f"[WARN] 쿠키 삭제 실패: {e}")


def fix_netscape_cookie_format(input_path: str, output_path: str) -> None:
    with open(input_path, "r", encoding="utf-8") as f_in, open(
        output_path, "w", encoding="utf-8"
    ) as f_out:
        for line in f_in:
            if line.startswith("#") or line.strip() == "":
                f_out.write(line)
                continue

            parts = line.strip().split("\t")
            if len(parts) != 7:
                print(f"[경고] 잘못된 형식으로 무시됨: {line.strip()}")
                continue

            domain = parts[0]
            domain_flag = "TRUE" if domain.startswith(".") else "FALSE"
            parts[1] = domain_flag

            try:
                parts[4] = str(int(float(parts[4])))
            except ValueError:
                print(f"[경고] expires 변환 실패: {parts[4]}")
                continue

            f_out.write("\t".join(parts) + "\n")
