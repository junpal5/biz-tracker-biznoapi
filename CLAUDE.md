# biz-tracker-biznoapi

bizno.net API를 사용하는 사업자 상세정보 일괄 조회 서비스. 단일 HTML 파일 (`index.html`), 빌드 시스템 없음.

## 개요

- **참조 저장소**: `junpal5/biz-tracker` (디자인 시스템 및 UX 패턴)
- **사용 API**: bizno.net (무료: `fapi`, 유료: `papi`)
- **API 키**: 내부 하드코딩 (`BIZNO_API_KEY` 상수) — 무료/유료 동일 키
- **인증**: 로그인 비밀번호 `gallup1974` (세션마다 재입력 필요 — localStorage 미사용)

## 아키텍처

단일 HTML 파일로 구성:
- **CSS**: MiniMax 디자인 토큰 (`--color-*`, `--space-*`, `--rounded-*`), DM Sans 폰트
- **JS**: 라이브러리 없이 바닐라 JS, SheetJS (`xlsx-0.20.3`) 엑셀 파싱/내보내기
- **빌드**: 없음. `index.html` 직접 편집 후 커밋/푸시

## bizno.net API 스펙

### 엔드포인트
- 무료: `https://bizno.net/api/fapi`
- 유료: `https://bizno.net/api/papi`

### 요청 파라미터
| 파라미터 | 설명 | 값 |
|---------|------|-----|
| `key`   | API 인증키 (필수) | `BIZNO_API_KEY` 상수 |
| `gb`    | 검색 유형 (필수) | 1=사업자등록번호, 2=법인등록번호, 3=상호명 |
| `q`     | 검색어 (필수) | 사업자번호 또는 상호명 (**`query`가 아님**) |
| `type`  | 응답 형식 | `json` 고정 |
| `page`, `pagecnt` | 페이징 | 선택사항 |

### 응답 필드명
| 필드 | 설명 |
|------|------|
| `bno` | 사업자등록번호 |
| `company` | 상호명 |
| `ceo` | 대표자 |
| `BsttCd` | 사업자상태코드 (01=계속, 02=휴업, 03=폐업) |
| `bstt` | 사업자상태명칭 |
| `TaxTypeCd` | 과세유형코드 |
| `taxtype` | 과세유형명칭 |
| `cno` | 법인등록번호 |
| `EndDt` | 폐업일 |

### 오류 응답
```json
{ "resultCode": -2, "resultMsg": "파라메터 오류", "totalCount": 0, "items": "" }
```
- `resultCode < 0`: 오류 — `checkApiError()` 함수에서 처리
- `items`가 빈 문자열 `""` 또는 `null`일 수 있음 — `parseItems()` 함수에서 처리

## 주요 함수

### API 호출 계층
```
callBizno(query, gb)        -- 원시 API 호출 (q= 파라미터 사용)
  ├── searchByName(name)    -- gb=3 (상호명 검색)
  ├── getDetail(bizno)      -- gb=1 (사업자등록번호 조회)
  └── searchByNameRaw(name, gb)  -- 테스트용 원시 응답 반환
```

### 흐름
1. 엑셀 업로드 → 헤더 파싱 → 사업자번호/회사명 열 선택
2. **사업자번호 있음** → `getDetail(bizno)` (gb=1) 직접 조회
3. **사업자번호 없음** → `searchByName(name)` (gb=3) → 결과 1건이면 자동 확정, 다건이면 disambiguation UI 표시
4. 확정된 사업자번호로 `getDetail()` → 결과 테이블 + XLSX 다운로드

### 필드 매핑
- `FIELD_KO`: API 필드명 → 한국어 컬럼명 (XLSX 내보내기 시 사용)
- `FIELD_ORDER`: 결과 테이블 우선 표시 순서

## 버전 히스토리

버전 정보는 `VERSION_HISTORY` 배열로 관리 (index.html 내부). 하단 버전 칩 클릭 시 모달로 확인 가능.

| 버전 | 날짜 | 주요 변경 |
|------|------|----------|
| 1.4.0 | 2026-05-21 | 홈 화면 + "사업자등록번호 조회" 페이지 추가 (Flask 프록시 + JS 채점 로직), server.py 추가 |
| 1.3.0 | 2026-05-20 | FIELD_KO 전면 확장(papi 전용 필드 한국어화), Excel 컬럼 순서 고정, 열 너비 자동 조정 |
| 1.2.0 | 2026-05-14 | API 키 입력창 제거, 테스트 패널 상단 이동, 버전 히스토리 추가 |
| 1.1.0 | 2026-05-14 | API 파라미터 수정 (query→q, gb 값 수정, 응답 필드명 수정) |
| 1.0.0 | 2026-05-13 | 최초 출시 |

## 개발 가이드

### 코드 수정
```bash
# 파일 편집 후 커밋/푸시
git add index.html
git -c commit.gpgsign=false commit -m "메시지"
git push -u origin main
```

### 버전 업데이트 시
1. `index.html`의 `VERSION_HISTORY` 배열 맨 앞에 새 항목 추가
2. 하단 버전 칩 HTML (`v1.x.x`)도 함께 업데이트
3. `CLAUDE.md`의 버전 히스토리 테이블도 업데이트

### 알려진 주의사항
- API 응답 `items` 필드는 결과가 없을 때 빈 문자열 `""` 또는 배열로 올 수 있음 (`parseItems()` 처리)
- `gb` 파라미터: 1=사업자번호, 2=법인번호, **3=상호명** (2는 앱에서 미사용)
- 검색어 파라미터명은 `q` (NOT `query`)
- git commit signing이 비활성화되어 있어 `-c commit.gpgsign=false` 플래그 필요

## 저장소 정보

- **GitHub**: `junpal5/biz-tracker-biznoapi`
- **브랜치**: `main`
- **배포**: GitHub Pages 또는 정적 호스팅 (단일 HTML 파일)
