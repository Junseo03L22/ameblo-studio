# 구조 분석과 독립 구현 결정

확인일: 2026-09-27. 원본 소스의 구현을 가져오지 않고 공개 구조 문서·메타데이터·라이선스를 읽었습니다.

## 원본에서 확인한 경계

Better Life Naver는 Electron/TypeScript 데스크톱 구조이며 renderer와 main을 IPC로 연결합니다. 생성, 이미지 처리, 브라우저 자동화, 설정/계정 서비스가 분리되어 있습니다. 구조 문서는 생성·자동화 모듈의 큰 파일과 결합도를 개선할 대상으로 기록하고 있습니다.

이번 앱은 사용자 요청의 범위에 맞춰 **생성 / 본문 조립 / 게시 / GUI / 로컬 저장**을 각각 작은 Python 모듈로 나눴습니다. 웹 크롤러, 예약 스케줄러, 댓글, 자동 이미지 생성, 원본의 상용 계정 관리 구조는 포함하지 않았습니다.

출처:
- https://github.com/cd000242-sudo/naver/blob/main/ARCHITECTURE.md
- https://github.com/cd000242-sudo/naver/blob/main/package.json
- https://github.com/cd000242-sudo/naver/blob/main/LICENSE
- https://github.com/cd000242-sudo/naver/blob/main/COMMERCIAL-LICENSING.md

원본 LICENSE는 AGPL v3 본문이며 상용 안내는 AGPL-3.0-or-later 또는 별도 계약 가능성을 명시합니다. 이 프로젝트는 원본 코드·프롬프트·에셋 없이 독립 작성했습니다. 원본의 코드 구조를 줄 단위로 변환하거나 포팅하지 않았습니다.

## 새 앱 데이터 흐름

```
Brief + Template
      │
      ├── topic + notes + 금지 시술명 → AI API → Copy(title/intro/closing)
      │                                      │
      └── 가격/시술명/이벤트 고정 ───────────────┤
                                             ▼
                                   Draft + ImagePlacement
                                             │
                                   validate → render_html
                                             │
                           GUI 미리보기 + 검수 fingerprint
                                             │
                           Playwright 전용 persistent profile
                                             │
                    이미지 한 장씩 업로드 → 서버 URL 수집
                                             │
                              본문 조립 → 입력값 일치 검증
                                             │
                              브라우저 검수 완료 사용자 신호
                                             │
                  draft 버튼 / 확인된 draft 라디오 → 저장 클릭
                                             │
                      완료 메시지 확인 → confirmed receipt
```

공개 발행은 설정 허용 + 이번 작업 선택 + 공개 확인 + 실제 브라우저 검수 + 전체 공개 라디오 확인이 모두 필요합니다.

## 상태와 경계

- AI 출력은 JSON schema와 로컬 검사로 제한합니다. 임의 HTML을 공급자에게 생성시키지 않습니다.
- 고정 가격·시술명은 사용자 입력값을 HTML escape하여 렌더링합니다.
- 이미지 파일 SHA-256까지 미리보기 fingerprint에 포함합니다. 같은 경로 파일이 변경되어도 재검수가 필요합니다.
- GUI 메인 스레드와 네트워크/브라우저 QThread를 분리합니다. Playwright 객체는 작업 스레드 안에서만 사용합니다.
- 브라우저 검수 중 입력·설정 변경을 막고 초안의 스냅샷을 사용합니다.
- 저장 클릭 전에 상태를 unknown으로 기록합니다. 클릭 타임아웃을 성공/실패로 단정하지 않습니다.
- 실패 시 브라우저를 정리합니다. 개인정보가 담길 수 있는 페이지 HTML이나 쿠키는 로그로 덤프하지 않습니다.
- 스크린샷은 로컬 저장하며 password 입력칸을 마스킹합니다.
- 사용자 설정/프로필은 프로젝트 폴더 밖 OS별 데이터 폴더에 저장하고 배포 ZIP에서 제외합니다.
- 동일 프로필의 병렬 사용과 앱 중복 실행을 파일 잠금으로 막습니다.

## 의도적인 MVP 한계

- 이벤트·가격표·병원 고정문구는 일본어로 직접 확정합니다. 한국어 원문 전체를 자동 번역하는 기능은 없습니다.
- AI의 의미 수준의 모든 의료적 오류를 판별하지 못합니다. 수치/금액 패턴과 일부 위험 표현 검사입니다.
- 사진의 의료적 적합성, 시술 전후 사진 규정, 법적 요건을 자동 판정하지 않습니다.
- Ameblo의 iframe/contenteditable 리치 에디터를 대상으로 합니다. 실제 로그인 후 DOM 호환성은 미확인입니다.
- 이미지 자동 업로드는 일반적인 파일 입력 + 새 썸네일 클릭/자동 삽입 경로를 구현했습니다. 기존 이미지 갤러리에서 재선택만 가능한 UI는 선택자 이상의 어댑터 수정이 필요할 수 있습니다.
- 예약 발행, 카테고리/테마 선택, 계정 간 공유 초안 서버는 없습니다.
- API 모의 응답 테스트를 사용하며 실제 키로 생성 호출은 하지 않았습니다.

## API/플랫폼 문서

- OpenAI Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- Gemini generateContent: https://ai.google.dev/api/generate-content
- Playwright 입력: https://playwright.dev/python/docs/input
- Qt/PyInstaller: https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html
