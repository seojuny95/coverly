import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { InsuranceAnalysisPage } from "./insurance-analysis-page";
import { saveInsuranceAnalysis } from "./insurance-analysis-store";
import type { UploadInsurance } from "../insurance-upload/insurance-upload-form";

const insuranceFile = new File(["%PDF-1.7"], "insurance.pdf", {
  type: "application/pdf",
});

describe("InsuranceAnalysisPage", () => {
  afterEach(() => {
    window.sessionStorage.clear();
  });

  test("shows insurance counts by classification", async () => {
    saveInsuranceAnalysis({
      generatedAt: "2026-07-09T07:30:00.000Z",
      selectedName: "테스트고객",
      insuranceDocuments: [
        {
          id: "insurance-1",
          fileName: "health.pdf",
          result: {
            status: "accepted",
            문자수: 100,
            기본정보: {
              보험사: "삼성화재",
              상품명: "건강보험",
              피보험자: "테스트고객",
              보험분류: "상해·질병·실손",
              상품태그: ["질병"],
            },
          },
        },
        {
          id: "insurance-2",
          fileName: "auto.pdf",
          result: {
            status: "accepted",
            문자수: 80,
            기본정보: {
              보험사: "현대해상화재보험",
              상품명: "개인용자동차보험",
              피보험자: "테스트고객",
              보험분류: "자동차",
              상품태그: ["자동차"],
            },
          },
        },
      ],
    });

    render(<InsuranceAnalysisPage />);

    expect(
      await screen.findByText("내 보험을 종류별로 정리했어요"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("테스트고객님의 보험 2개를 종류별로 보기 쉽게 정리했어요."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "보험증권 더 올리기" }),
    ).toBeInTheDocument();

    const autoCard = screen.getAllByText("자동차")[0].closest("div");
    const healthCard = screen.getAllByText("상해·질병·실손")[0].closest("div");

    expect(autoCard).not.toBeNull();
    expect(healthCard).not.toBeNull();
    expect(within(autoCard as HTMLElement).getByText("1")).toBeInTheDocument();
    expect(
      within(healthCard as HTMLElement).getByText("1"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("자동차").length).toBeGreaterThan(1);
  });

  test("expands a insurance row to show detail fields", async () => {
    saveInsuranceAnalysis({
      generatedAt: "2026-07-09T07:30:00.000Z",
      insuranceDocuments: [
        {
          id: "insurance-1",
          fileName: "health.pdf",
          result: {
            status: "accepted",
            문자수: 100,
            기본정보: {
              보험사: "삼성화재",
              상품명: "건강보험",
              증권번호: "POLICY-TEST-001",
              계약자: "가나",
              피보험자: "가나",
              보험분류: "상해·질병·실손",
              상품태그: ["질병", "어린이"],
              납입기간: "20년납",
              만기일: "2046-01-01",
              보험기간: {
                시작일: "2026-01-01",
                종료일: "2046-01-01",
              },
              보험료: {
                금액: 120000,
                납입주기: "월납",
              },
            },
          },
        },
      ],
    });

    render(<InsuranceAnalysisPage />);

    const row = await screen.findByRole("button", {
      name: /건강보험/,
    });
    expect(row).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("질병")).toBeInTheDocument();
    expect(screen.getByText("어린이")).toBeInTheDocument();

    fireEvent.click(row);

    expect(row).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("POLICY-TEST-001")).toBeInTheDocument();
    expect(screen.getByText("2026-01-01 - 2046-01-01")).toBeInTheDocument();
    expect(screen.getByText("월납 120,000원")).toBeInTheDocument();
    expect(screen.queryByText("상품명")).not.toBeInTheDocument();
    expect(screen.queryByText("상품태그")).not.toBeInTheDocument();
  });

  test("renders every display field and insurer logo when an insurance document has full data", async () => {
    saveInsuranceAnalysis({
      generatedAt: "2026-07-09T07:30:00.000Z",
      selectedName: "테스트고객A",
      insuranceDocuments: [
        {
          id: "insurance-full",
          fileName: "db-driver.pdf",
          result: {
            status: "accepted",
            문자수: 200,
            기본정보: {
              보험사: "삼성화재해상보험주식회사",
              상품명: "마이헬스파트너",
              증권번호: "POLICY-TEST-002",
              계약자: "테스트고객A",
              피보험자: "테스트고객A",
              보험분류: "상해·질병·실손",
              상품태그: ["질병", "어린이"],
              납입기간: "20년납",
              만기일: "2027-01-01",
              보험기간: {
                시작일: "2026-01-01",
                종료일: "2027-01-01",
              },
              보험료: {
                금액: 120000,
                납입주기: "월납",
              },
            },
          },
        },
      ],
    });

    const { container } = render(<InsuranceAnalysisPage />);

    const row = await screen.findByRole("button", {
      name: /마이헬스파트너/,
    });

    expect(screen.getByText("db-driver.pdf")).toBeInTheDocument();
    expect(screen.getByText("질병")).toBeInTheDocument();
    expect(screen.getByText("어린이")).toBeInTheDocument();

    const logo = container.querySelector('img[src*="samsung-fire.png"]');
    expect(logo).not.toBeNull();

    fireEvent.click(row);

    const detail = row.closest("div");
    expect(detail).not.toBeNull();
    expect(screen.getByText("보험사")).toBeInTheDocument();
    expect(screen.getByText("삼성화재해상보험주식회사")).toBeInTheDocument();
    expect(screen.getByText("증권번호")).toBeInTheDocument();
    expect(screen.getByText("POLICY-TEST-002")).toBeInTheDocument();
    expect(screen.getByText("계약자")).toBeInTheDocument();
    expect(screen.getAllByText("테스트고객A").length).toBeGreaterThan(1);
    expect(screen.getByText("피보험자")).toBeInTheDocument();
    expect(screen.getByText("보험기간")).toBeInTheDocument();
    expect(screen.getByText("2026-01-01 - 2027-01-01")).toBeInTheDocument();
    expect(screen.getByText("만기일")).toBeInTheDocument();
    expect(screen.getByText("2027-01-01")).toBeInTheDocument();
    expect(screen.getByText("납입기간")).toBeInTheDocument();
    expect(screen.getByText("20년납")).toBeInTheDocument();
    expect(screen.getByText("보험료")).toBeInTheDocument();
    expect(screen.getByText("월납 120,000원")).toBeInTheDocument();
  });

  test("renders DB insurer name and logo for a parsed driver insurance document", async () => {
    saveInsuranceAnalysis({
      generatedAt: "2026-07-09T07:30:00.000Z",
      selectedName: "테스트고객A",
      insuranceDocuments: [
        {
          id: "db-driver-insurance",
          fileName: "DB운전자보험증권.pdf",
          result: {
            status: "accepted",
            문자수: 200,
            기본정보: {
              보험사: "DB손해보험",
              상품명: "무배당 프로미라이프 참좋은운전자상해보험(TM)2404",
              증권번호: "POLICY-TEST-MASKED-001",
              계약자: "테스트고객A",
              피보험자: "테스트고객A",
              보험분류: "배상·화재·기타",
              상품태그: ["운전자"],
              납입기간: "20년납",
              만기일: "2044-07-26",
              보험기간: {
                시작일: "2024-07-26",
                종료일: "2044-07-26",
              },
              보험료: {
                금액: 11670,
                납입주기: "월납",
              },
            },
          },
        },
      ],
    });

    const { container } = render(<InsuranceAnalysisPage />);
    const row = await screen.findByRole("button", {
      name: /무배당 프로미라이프 참좋은운전자상해보험/,
    });

    expect(
      container.querySelector('img[src*="db-insurance.png"]'),
    ).not.toBeNull();

    fireEvent.click(row);

    expect(screen.getByText("보험사")).toBeInTheDocument();
    expect(screen.getByText("DB손해보험")).toBeInTheDocument();
    expect(screen.getByText("증권번호")).toBeInTheDocument();
    expect(screen.getByText("POLICY-TEST-MASKED-001")).toBeInTheDocument();
    expect(screen.getByText("보험기간")).toBeInTheDocument();
    expect(screen.getByText("2024-07-26 - 2044-07-26")).toBeInTheDocument();
    expect(screen.getByText("보험료")).toBeInTheDocument();
    expect(screen.getByText("월납 11,670원")).toBeInTheDocument();
  });

  test("shows an empty state when no analysis exists", async () => {
    render(<InsuranceAnalysisPage />);

    expect(
      await screen.findByText("분석할 보험증권이 없어요"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "보험증권 올리기" }),
    ).toHaveAttribute("href", "/upload");
  });

  test("opens an upload modal and merges uploaded insuranceDocuments into the current analysis", async () => {
    const user = userEvent.setup();
    const uploadInsurance = vi.fn<UploadInsurance>().mockResolvedValue({
      status: "accepted",
      문자수: 80,
      기본정보: {
        보험사: "현대해상화재보험",
        상품명: "개인용자동차보험",
        피보험자: "테스트고객",
        보험분류: "자동차",
        상품태그: ["자동차"],
      },
    });

    saveInsuranceAnalysis({
      generatedAt: "2026-07-09T07:30:00.000Z",
      selectedName: "테스트고객",
      insuranceDocuments: [
        {
          id: "insurance-1",
          fileName: "health.pdf",
          result: {
            status: "accepted",
            문자수: 100,
            기본정보: {
              보험사: "삼성화재",
              상품명: "건강보험",
              피보험자: "테스트고객",
              보험분류: "상해·질병·실손",
              상품태그: ["질병"],
            },
          },
        },
      ],
    });

    render(<InsuranceAnalysisPage uploadInsurance={uploadInsurance} />);

    await user.click(
      await screen.findByRole("button", { name: "보험증권 더 올리기" }),
    );

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "보험증권 더 올리기" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("테스트고객(피보험자)의 보험증권 PDF만 올릴 수 있어요"),
    ).toBeInTheDocument();
    expect(screen.queryByText("보험증권 PDF")).not.toBeInTheDocument();

    await user.upload(screen.getByLabelText("PDF 파일 선택"), insuranceFile);
    await user.click(screen.getByRole("button", { name: "분석에 추가하기" }));

    expect(uploadInsurance).toHaveBeenCalledWith(insuranceFile);
    expect(
      await screen.findByText(
        "테스트고객님의 보험 2개를 종류별로 보기 쉽게 정리했어요.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getAllByText("자동차").length).toBeGreaterThan(1);
  });
});
