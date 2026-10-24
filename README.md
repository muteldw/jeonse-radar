# 전세 레이더 9

신안아파트(2027.4 만기) 이후 이사 후보를 찾기 위한 전세 추천 프로그램.
서울 25개 구와 안양(만안·동안)의 아파트·빌라 전용 80㎡↑(34평형대 이상) 전세·매매 실거래를 매일 06:00(KST)에 수집해 단지별 추천 순위를 만들고,
휴대폰·PC 공용 웹(PWA)으로 보여준다.

## 구조

```
config.json                 지역·예산·면적 조건, 단지별 역 정보
collector/fetch_rent.py     국토부 아파트·연립다세대 전월세 실거래 → data/rent_raw.csv (지역별 이어받기: data/collect_state.json)
collector/geo.py            카카오 로컬 API 위치·역·인프라 → data/geo.json
collector/fetch_sale.py     국토부 아파트·연립다세대 매매 실거래 → data/sale_raw.csv
model/rank_sale.py          매매 추천(매매가·전세가율·갭·1년 상승률) → web/data/sale.json + sale/<생활권>.json
notify/dispatch.py          알림 발송기: config/notify.json 의 주기·켜기/끄기·받는 사람대로 발송
notify/telegram.py, email_alert.py  채널별 발송
config/notify.json          알림 설정 (웹 '알림 설정' 화면에서 만들어 붙여넣기)
config/loan_rules.json      LTV·대출 한도·DSR·취득세 규칙 (제도 바뀌면 여기만 수정)
config/wealth_dist.json     순자산 → 상위 % 추정 기준점
model/rank.py               전세 추천 점수·취향 학습 → web/data/recommend.json(목록) + rec/<생활권>.json
model/stats.py              월별 통계(단지 보정 지수·평당가·거래량·갱신 비중, 전년 동월 비교) → web/data/stats.json
model/supply.py             계약기간·갱신율로 단지별 월별 예상 매물, 계절 시세 → web/data/supply.json
web/                        화면: 추천(index) · 매매(buy) · 지도(map) · 이사 시기(timing) · 매수자 분석(buyer) · 알림 설정(settings)
data/feedback.json          관심/제외 기록 (화면의 '기록 복사' 내용을 붙여넣기)
.github/workflows/daily.yml  매일 06:00 KST 수집·계산·화면 배포
.github/workflows/notify.yml KST 06~22시 매시 5분 알림 발송 (수동 실행 시 즉시 발송)
tests/                      모의 데이터 테스트
```

## 처음 설정 (한 번만)

1. **API 키 발급**: 공공데이터포털(data.go.kr)에서 `국토교통부_아파트 전월세 실거래가 자료` 활용신청 (빌라·매매는 `연립다세대 전월세`, `아파트 매매`, `연립다세대 매매` 자료도 각각 신청, 키는 하나) → 마이페이지에서 일반 인증키(Decoding) 복사. 승인은 보통 즉시~1시간.
2. **키 등록**: GitHub 저장소 → Settings → Secrets and variables → Actions → New repository secret
   - Name: `MOLIT_API_KEY`, Value: 복사한 키
3. **Pages 켜기**: Settings → Pages → Source를 `GitHub Actions`로 선택.
4. **첫 실행**: Actions 탭 → `daily-recommend` → Run workflow. 첫 실행은 24개월치를 받느라 몇 분 걸린다.
5. 휴대폰에서 Pages 주소를 열고 '홈 화면에 추가'하면 앱처럼 쓸 수 있다.

## 2단계 선택 기능 (키를 넣으면 자동으로 켜짐)

| Secret 이름 | 용도 | 발급 |
|---|---|---|
| `KAKAO_REST_KEY` | 단지 위치, 가까운 역·도보시간, 학교·어린이집·마트·병원 수 | developers.kakao.com → 앱 추가 → REST API 키. 앱 설정에서 '카카오맵' 사용 설정 ON |
| `TELEGRAM_BOT_TOKEN` | 매일 아침 TOP 5 알림 | 텔레그램 @BotFather → /newbot |
| `TELEGRAM_CHAT_ID` | 알림 받을 대화방 | 봇에게 메시지를 보낸 뒤 Actions를 실행하면 로그에 chat id가 출력됨 |
| `GMAIL_USER`, `GMAIL_APP_PASSWORD` | 메일 발송 계정 | 구글 2단계 인증 후 myaccount.google.com/apppasswords |
| `MAIL_RECIPIENTS` | 받는 사람 목록 | `본인=a@gmail.com, 배우자=b@naver.com` — 별칭은 알림 설정 화면에서 사용 |

## 조건 바꾸기

`config.json`에서 `budget_eok`(예산, 억), `min_area_m2`, `regions`(법정동 코드 앞 5자리)를 수정한다.
새 지역은 `regions`에 코드를 넣고 `areas`에 생활권(이름·구 목록·기준역 좌표)을 추가하면 다음 실행에서 24개월치를 소급 수집한다.
규제지역 목록은 `config/loan_rules.json`의 `regulated_sgg`에 있다(여기 없는 수도권 지역은 비규제로 계산).
역 정보는 `complex_meta`에 단지명으로 추가한다(2단계에서 카카오맵 API로 자동화 예정).

## 로컬 테스트

```
pip install -r requirements.txt
python tests/test_pipeline.py
python tests/make_sample.py      # 예시 데이터로 화면 확인
cd web && python -m http.server  # http://localhost:8000
```

## 로드맵

1. 실거래 수집 + 추천 화면 + 매일 자동 실행 (완료)
2. 카카오맵 역·인프라 자동 계산, 텔레그램 아침 알림 (코드 완료, 키 등록 필요)
3. 매수자 자금 분석·지도·알림 설정 (완료) → 다음: 가격 전망 모델(LightGBM), 피드백 자동 저장
4. 위험 필터(전세가율·등기), 시계열 딥러닝 모델 시험
