def fix_netscape_cookie_format(input_path: str, output_path: str) -> None:
    with open(input_path, "r", encoding="utf-8") as f_in, open(output_path, "w", encoding="utf-8") as f_out:
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
