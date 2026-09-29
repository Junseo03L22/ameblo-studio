# Ameblo 선택자와 실제 검증 경계

## 확인된 것과 미확인된 것

2026-09-27 공개 요청으로 다음 글쓰기 주소에 접근했을 때 `auth.user.ameba.jp/signin`으로 이동했습니다. 페이지 제목은 `ログインする | Ameba`, 로그인 필드 이름은 `accountId`, `password`였습니다. 로그인 정보는 입력하지 않았습니다. URL의 nonce/state/CSRF 등 인증용 값은 문서에 보관하지 않습니다.

https://blog.ameba.jp/ucs/entry/srventryinsertinput.do

인증 후 title/body/upload/save DOM은 확인하지 못했습니다. `selectors.py`의 값은 의미 기반 후보와 fallback이며 확인된 실제 DOM이라고 주장하지 않습니다. 로그인 화면을 찾았다는 사실만으로 게시 호환성이 증명되지 않습니다.

Ameba 공식 도움말에서 제목/본문/이미지/공개 범위 구성, PC 이미지 업로드 뒤 썸네일 클릭, 초안 저장 방식을 참고했습니다. 도움말의 갱신일이 오래되어 현재 UI와 차이가 있을 수 있습니다.

- https://helps.ameba.jp/qguide/blog/post_1086.html
- https://helps.ameba.jp/faq/blog/article/post_1033.html
- https://helps.ameba.jp/faq/blogrp/2290/post_1265.html
- https://helps.ameba.jp/blog_a09.html

## 설정 파일

앱 **설정 → 고급 · DOM 선택자**에서 편집합니다. 저장한 JSON은 앱 데이터 폴더의 `selectors.json`이며 기본값을 덮어씁니다. 아래 키별로 Playwright 선택자 문자열 배열을 제공합니다.

| 키 | 대상 / 조건 |
|---|---|
| title | 제목 input 또는 textarea, 유일한 보이는 요소 |
| body | 리치 본문 contenteditable. iframe 내부도 탐색 |
| image_input | 파일 input, 숨겨진 input도 허용. 여러 개면 범위를 좁혀야 함 |
| image_tab | 이미지 업로드 패널을 여는 버튼/탭 |
| draft_button | 명확한 `下書き保存` 동작만 연결 |
| draft_radio | 실제 input[type=radio], 체크 상태 확인 가능해야 함 |
| public_radio | 실제 전체 공개 라디오 |
| submit_button | 공개 또는 확인된 초안 모드에서만 사용하는 최종 제출 |
| draft_success | 이번 저장 후 나타나는 초안 완료 메시지 |
| public_success | 이번 발행 후 나타나는 공개 완료 메시지 |

각 배열의 앞쪽 후보부터 확인합니다. 한 후보에 둘 이상이 일치하면 잘못된 요소를 고르지 않고 중단합니다. 일반 `[contenteditable=true]`는 마지막 fallback이며 여러 편집 요소가 있으면 더 구체적인 selector가 필요합니다.

## 보정 절차

1. 앱의 공개 기능을 끕니다. 실제 내용 대신 테스트용 새 글을 사용합니다.
2. 로그인 후 Chromium 개발자 도구에서 제목, 본문, 이미지 input, 초안 저장 버튼을 확인합니다.
3. 테스트용 계정에서 각 선택자의 일치 개수와 실제 요소를 확인합니다. 본문이 iframe 안에 있으면 프레임 내부 요소의 selector만 설정합니다.
4. 설정에 정확한 후보를 앞쪽에 추가합니다. 일반 `button[type=submit]`을 draft_button으로 지정하면 안 됩니다.
5. **본문만** 먼저 시도합니다. 저장 전에 실제 브라우저 검수가 나타나는지 확인합니다.
6. 이미지 1장, 이미지 여러 장, 동일 위치 이미지 순서, 서로 다른 본문 위치를 확인합니다.
7. 임시저장 후 실제 글 목록의 비공개 상태와 재열기 후 본문을 확인합니다.
8. 정확한 완료 문구가 다르면 success selector를 보정합니다. 이미 저장된 경우 자동 재시도하지 않습니다.
9. 공개 발행은 별도의 테스트 글에서 의도적으로 검증합니다.

## 이미지 어댑터

파일 하나를 업로드한 뒤 본문에 자동 삽입된 이미지를 읽습니다. 자동 삽입이 없으면 업로드 전후를 비교해 새로 나타난 유일한 Ameba 이미지 썸네일을 클릭하고, 본문에 들어온 실제 이미지 URL을 수집합니다. `https://stat.ameba.jp/...` 계열만 허용합니다. 썸네일이 여럿 생기거나 CDN/갤러리 동작이 바뀌면 중단하므로 `publisher.upload_image` 어댑터 수정이 필요할 수 있습니다.

모든 이미지 URL을 얻은 뒤 미리보기와 같은 순서/위치로 본문을 조립합니다. 저장 전에 제목, 본문 텍스트, 이미지 URL 순서, 본문 내 이미지 위치를 다시 검사합니다. 사용자 브라우저 수정이 앱 초안에 반영되는 양방향 편집은 지원하지 않습니다.

## 진단과 실패 의미

`diagnostics/<시각>/error.json`에는 실패 단계, 예외 종류, 저장 시도 여부가 기록됩니다. 가능하면 `screen.png`가 함께 생성됩니다. `confirm_result` 실패는 실제 저장이 이미 됐을 수 있다는 뜻입니다. 로컬 receipt가 unknown이면 Ameblo에서 글 목록을 확인하세요.

브라우저 시작 오류는 선택자 문제가 아닐 수 있습니다. Chromium 미설치, 기업 보안 정책, macOS 작업 샌드박스 제한 등을 확인하세요. 앱은 해당 보안 제한을 우회하지 않습니다.
