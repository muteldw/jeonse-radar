# 전세 레이더 9

신안아파트(2027.4 만기) 이후 이사 후보를 찾기 위한 전세 추천 프로그램.
강서·양천 전용 80㎡↑(34평형대 이상) 전세 실거래를 매일 06:00(KST)에 수집해 단지별 추천 순위를 만들고,
휴대폰·PC 공용 웹(PWA)으로 보여준다.

## 구조

```
config.json                 지역·예산·면적 조건, 단지별 역 정보
collector/fetch_rent.py     국토부 아파트 전월세 실거래 API 수집 → data/rent_raw.csv
model/rank.py               단지별 집계·추천 점수·취향 학습 → web/data/recommend.json
web/                        화면 (GitHub Pages로 배포)
data/feedback.json          관심/제외 기록 (화면의 '기록 복사' 내용을 붙여넣기)
.github/workflows/daily.yml 매일 06:00 KST 자동 실행
tests/                      모의 데이터 테스트
```

## 처음 설정 (한 번만)

1. **API 키 발급**: 공공데이터포털(data.go.kr)에서 `국토교통부_아파트 전월세 실거래가 자료` 활용신청 → 마이페이지에서 일반 인증키(Decoding) 복사. 승인은 보통 즉시~1시간.
2. **키 등록**: GitHub 저장소 → Settings → Secrets and variables → Actions → New repository secret
   - Name: `MOLIT_API_KEY`, Value: 복사한 키
3. **Pages 켜기**: Settings → Pages → Source를 `GitHub Actions`로 선택.
4. **첫 실행**: Actions 탭 → `daily-recommend` → Run workflow. 첫 실행은 24개월치를 받느라 몇 분 걸린다.
5. 휴대폰에서 Pages 주소를 열고 '홈 화면에 추가'하면 앱처럼 쓸 수 있다.

## 조건 바꾸기

`config.json`에서 `budget_eok`(예산, 억), `min_area_m2`, `regions`(법정동 코드 앞 5자리)를 수정한다.
역 정보는 `complex_meta`에 단지명으로 추가한다(2단계에서 카카오맵 API로 자동화 예정).

## 로컬 테스트

```
pip install -r requirements.txt
python tests/test_pipeline.py
python tests/make_sample.py      # 예시 데이터로 화면 확인
cd web && python -m http.server  # http://localhost:8000
```

## 로드맵

1. 실거래 수집 + 추천 화면 + 매일 자동 실행 (현재)
2. 카카오맵 역·인프라 자동 계산, 텔레그램 아침 알림
3. 가격 전망 모델(LightGBM) 학습·백테스트, 피드백 자동 저장
4. 위험 필터(전세가율·등기), 시계열 딥러닝 모델 시험
