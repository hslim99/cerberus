import os
import shutil
import tempfile

from dotenv import load_dotenv

load_dotenv()

temp_cookie_path = None


def generate_temp_cookie() -> str:
    global temp_cookie_path

    cookie_path = os.getenv("COOKIEFILE")
    if cookie_path and os.path.isfile(cookie_path):
        temp_cookie = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        shutil.copyfile(cookie_path, temp_cookie.name)
        temp_cookie_path = temp_cookie.name
    else:
        temp_cookie_path = None

    return temp_cookie_path


def cleanup_temp_cookie():
    global temp_cookie_path
    if temp_cookie_path and os.path.exists(temp_cookie_path):
        try:
            os.remove(temp_cookie_path)
            print(f"[쿠키 삭제] {temp_cookie_path}")
        except Exception as e:
            print(f"[쿠키 삭제 실패] {e}")
        finally:
            temp_cookie_path = None


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
