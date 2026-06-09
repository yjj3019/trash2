#!/usr/bin/env python3
 
import os
import shutil
import datetime
import argparse
import glob
import hashlib
 
def calculate_md5(file_path):
    """파일의 MD5 체크섬을 계산하는 함수"""
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        return f"md5_error: {e}"
 
# 우선순위 디렉토리 목록 (순서대로 높은 우선순위)
PRIORITY_DIRS = [
    "rhel-7-server-rpms",
    "rhel-8-for-x86_64-baseos-rpms",
    "rhel-8-for-x86_64-appstream-rpms",
    "rhel-9-for-x86_64-baseos-rpms",
    "rhel-9-for-x86_64-appstream-rpms",
    "rhel-10-for-x86_64-baseos-rpms",
    "rhel-10-for-x86_64-appstream-rpms"
]
 
def get_priority_score(file_path):
    """
    파일 경로를 분석하여 우선순위 점수를 반환합니다.
    점수가 낮을수록 높은 우선순위를 가집니다.
    """
    path_parts = file_path.split(os.sep)
    for i, p_dir in enumerate(PRIORITY_DIRS):
        if p_dir in path_parts:
            return i
    return len(PRIORITY_DIRS)  # 목록에 없는 디렉토리면 가장 낮은 우선순위 부여
 
def main():
    # 1. 커맨드라인 인자 설정
    parser = argparse.ArgumentParser(description="파일에 기록된 패키지 패턴을 찾아 /tmp/ 날짜 디렉토리에 복사합니다.")
    parser.add_argument('-l', '--list-file', required=True, help="복사할 패키지 패턴이 한 줄씩 기록된 파일 (예: packages.txt)")
    parser.add_argument('-s', '--src-dir', required=True, help="원본 파일들이 위치한 디렉토리 경로")
    parser.add_argument('-a', '--arch', default=None, help="패키지 아키텍처 지정 (예: x86_64, i686). 생략 시 모든 아키텍처 검색")
    args = parser.parse_args()
 
    list_file = args.list_file
    src_dir = args.src_dir
    arch = args.arch
 
    # 2. 유효성 검사
    if not os.path.exists(list_file):
        print(f"[오류] 패키지 목록 파일을 찾을 수 없습니다: {list_file}")
        return
 
    if not os.path.exists(src_dir):
        print(f"[오류] 원본 디렉토리를 찾을 수 없습니다: {src_dir}")
        return
 
    # 3. /tmp/(date) 형태의 목적지 디렉토리 생성
    # 날짜와 시간을 조합하여 고유한 폴더명 생성 (예: /tmp/0402-131300)
    now = datetime.datetime.now().strftime("%m%d-%H%M%S")
    dest_dir = f"/tmp/{now}"
 
    try:
        os.makedirs(dest_dir, exist_ok=True)
        print(f"[정보] 목적지 디렉토리가 생성되었습니다: {dest_dir}")
    except Exception as e:
        print(f"[오류] 목적지 디렉토리 생성 실패: {e}")
        return
 
    # 로그 파일 경로 설정
    log_file_path = os.path.join(dest_dir, "copy_result.log")
 
    # 4. 패키지 목록 파일 읽기
    with open(list_file, 'r', encoding='utf-8') as f:
        # 빈 줄과 앞뒤 공백 제거
        packages = [line.strip() for line in f if line.strip()]
 
    success_packages = []
    failed_packages = []
    copied_files_info = [] # 복사 성공한 개별 파일과 md5 정보를 담을 리스트
 
    print(f"[정보] 총 {len(packages)}개의 패키지 패턴을 검색합니다...\n")
 
    # 5. 복사 로직 수행 및 로깅
    with open(log_file_path, 'w', encoding='utf-8') as log_file:
        # 콘솔 출력과 로그 파일 기록을 동시에 하는 헬퍼 함수
        def log(msg):
            print(msg)
            log_file.write(msg + '\n')
 
        log(f"--- 패키지 복사 작업 시작 ({now}) ---")
        log(f"원본 디렉토리: {src_dir}")
        log(f"목적지 디렉토리: {dest_dir}")
        if arch:
            log(f"지정된 아키텍처: {arch}\n")
        else:
            log("지정된 아키텍처: 없음 (모든 파일 검색)\n")
 
        for pkg in packages:
            # 사용자가 입력한 패키지명에 와일드카드(*)가 있거나 확장자(.rpm)가 명시된 경우 그대로 사용
            if '*' in pkg or pkg.endswith('.rpm'):
                target_pattern = pkg
            else:
                # 아키텍처가 지정된 경우 아키텍처를 포함하여 검색, 없으면 기본 와일드카드 추가
                if arch:
                    target_pattern = f"{pkg}.{arch}*"
                else:
                    target_pattern = f"{pkg}*"
                 
            # 하위 디렉토리를 포함하여 재귀적으로 검색 (**)
            search_pattern = os.path.join(src_dir, '**', target_pattern)
            matched_files = glob.glob(search_pattern, recursive=True)
 
            # 디렉토리를 제외하고 실제 파일만 필터링
            matched_files = [f for f in matched_files if os.path.isfile(f)]
 
            if not matched_files:
                failed_packages.append(pkg)
                log(f"[실패] 매칭되는 파일을 찾을 수 없음: {pkg}")
            else:
                # 파일명이 동일한 중복 파일이 있을 경우 우선순위 디렉토리 기준으로 필터링
                files_by_basename = {}
                for f in matched_files:
                    basename = os.path.basename(f)
                    if basename not in files_by_basename:
                        files_by_basename[basename] = []
                    files_by_basename[basename].append(f)
 
                best_matched_files = []
                for basename, paths in files_by_basename.items():
                    if len(paths) > 1:
                        # 우선순위 점수가 낮은(우선순위가 높은) 순으로 정렬
                        paths.sort(key=get_priority_score)
                    # 가장 우선순위가 높은 1개의 파일만 최종 복사 대상으로 선택
                    best_matched_files.append(paths[0])
 
                copy_success = True
                for file_path in best_matched_files:
                    try:
                        # 파일 복사 (메타데이터 유지)
                        shutil.copy2(file_path, dest_dir)
                         
                        # 복사 성공 후 md5 해시 계산 및 정보 저장
                        filename = os.path.basename(file_path)
                        md5_hash = calculate_md5(file_path)
                        copied_files_info.append((filename, md5_hash))
                         
                        log(f"[복사] {filename} -> {dest_dir}")
                    except Exception as e:
                        log(f"[오류] {os.path.basename(file_path)} 복사 중 에러 발생: {e}")
                        copy_success = False
                 
                # 최소 1개 이상의 파일이 에러 없이 복사되었다면 성공으로 간주
                if copy_success:
                    success_packages.append(pkg)
                else:
                    failed_packages.append(pkg)
 
        # 6. 결과 요약 리포트
        log("\n==============================")
        log("         작업 결과 요약       ")
        log("==============================")
        log(f"  - 총 요청 패키지: {len(packages)}개")
        log(f"  - 복사 성공 패키지: {len(success_packages)}개")
        log(f"  - 복사 실패 패키지: {len(failed_packages)}개")
        log("==============================\n")
 
        if success_packages:
            log("[✅ 성공한 패키지 리스트]")
            for p in success_packages:
                log(f"  - {p}")
            log("")
 
        if failed_packages:
            log("[❌ 실패한 패키지 리스트]")
            for p in failed_packages:
                log(f"  - {p}")
 
    # 7. README.txt 생성 (성공한 파일명 및 md5sum 기록)
    readme_file_path = os.path.join(dest_dir, "README.txt")
    try:
        with open(readme_file_path, 'w', encoding='utf-8') as readme_file:
            readme_file.write("Successfully Copied Packages Info\n")
            readme_file.write("=========================================\n\n")
            if copied_files_info:
                for filename, md5 in copied_files_info:
                    # Linux md5sum 명령어 출력 포맷(md5해시값  파일명)과 동일하게 작성
                    readme_file.write(f"{md5}  {filename}\n")
            else:
                readme_file.write("No files were successfully copied.\n")
        print(f"[정보] 복사된 파일 목록 및 md5sum 정보가 담긴 README.txt가 생성되었습니다.")
    except Exception as e:
        print(f"[오류] README.txt 파일 생성 중 에러 발생: {e}")
 
    print(f"\n[완료] 복사 작업이 끝났습니다.")
    print(f"[정보] 상세 작업 로그가 생성되었습니다: {log_file_path}")
 
if __name__ == "__main__":
    main()
