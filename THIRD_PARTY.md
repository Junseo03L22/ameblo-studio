# 원본 및 의존성 고지

이 프로젝트 소스는 독립 구현이며 MIT로 제공합니다. Better Life Naver의 코드·프롬프트·이미지·아이콘을 복제하거나 포함하지 않았습니다.

구조 참고: https://github.com/cd000242-sudo/naver
원본 LICENSE: https://github.com/cd000242-sudo/naver/blob/main/LICENSE
원본 상용 안내: https://github.com/cd000242-sudo/naver/blob/main/COMMERCIAL-LICENSING.md
2026-09-27 확인: 원본은 AGPL-3.0-or-later, 권리자가 별도로 제공할 수 있는 상용 라이선스 안내가 있습니다. 이 프로젝트의 MIT는 원본이나 외부 라이브러리에 적용되지 않습니다.

주요 의존성은 각자의 라이선스를 유지합니다. 배포 시 실제 설치 버전의 라이선스 및 고지를 확인해야 합니다.

- PySide6 / Qt: LGPLv3 / GPLv3 / 상용 선택지. https://doc.qt.io/qtforpython-6/licenses.html
- Playwright Python: Apache-2.0. https://github.com/microsoft/playwright-python
- Chromium 및 FFmpeg 등 브라우저 번들: 여러 라이선스. 번들 내부 LICENSE/credits 고지 유지.
- Pillow: HPND 계열. https://github.com/python-pillow/Pillow
- python-dotenv: BSD-3-Clause. https://github.com/theskumar/python-dotenv
- platformdirs: MIT. https://github.com/tox-dev/platformdirs
- filelock: Unlicense. https://github.com/tox-dev/filelock
- PyInstaller: GPL 및 부트로더 배포 예외. https://pyinstaller.org/en/stable/license.html

패키징은 Qt 라이브러리가 분리되는 onedir 방식을 사용합니다. build.py는 설치된 패키지의 라이선스 파일과 버전 목록을 수집합니다. 수집 스크립트는 라이선스 준수 검토를 대신하지 않습니다. LGPL을 선택해 배포할 때 필요한 라이브러리 교체 가능성, 고지 및 해당 라이브러리 소스 제공 의무 등을 충족해야 합니다. Qt의 원본 라이선스와 브라우저 고지를 제거하지 마세요.

Ameblo Studio는 Ameba/CyberAgent 또는 Better Life Naver의 공식 앱이나 제휴 제품이 아닙니다.
