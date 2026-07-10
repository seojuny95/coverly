import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { PolicyCoverageList } from "./policy-coverage-list";
import type { PolicyCoverage } from "../policy-upload/upload-policy";

const GENERATED_NOTICE =
  "일반적인 설명이에요. 정확한 보장 내용은 가입한 상품의 약관에서 확인할 수 있어요.";

const withDetail: PolicyCoverage = {
  담보명: "암진단비",
  가입금액: "3,000만원",
  보장내용: "암 진단 확정 시 최초 1회 지급",
  해설: null,
};

const withExplanation: PolicyCoverage = {
  담보명: "교통사고처리지원금",
  가입금액: "5,000만원",
  보장내용: null,
  해설: "교통사고 형사합의금을 지원해요.",
};

const unverifiedAmount: PolicyCoverage = {
  담보명: "긴급출동서비스",
  가입금액: "확인필요",
  보장내용: null,
  해설: null,
};

describe("PolicyCoverageList", () => {
  test("renders name, policy wording, then amount in order", () => {
    render(<PolicyCoverageList coverages={[withDetail]} />);

    const item = screen.getByRole("listitem");
    const text = item.textContent ?? "";
    expect(text.indexOf("암진단비")).toBeGreaterThanOrEqual(0);
    expect(text.indexOf("암진단비")).toBeLessThan(
      text.indexOf("암 진단 확정 시 최초 1회 지급"),
    );
    expect(text.indexOf("암 진단 확정 시 최초 1회 지급")).toBeLessThan(
      text.indexOf("3,000만원"),
    );
  });

  test("keeps policy wording readable with preserved line breaks", () => {
    render(
      <PolicyCoverageList
        coverages={[{ ...withDetail, 보장내용: "지급 사유\n※ 유사암 제외" }]}
      />,
    );

    expect(screen.getByText(/지급 사유/)).toHaveClass("whitespace-pre-line");
  });

  test("does not show the generated notice for policy wording", () => {
    render(<PolicyCoverageList coverages={[withDetail]} />);

    expect(screen.queryByText(GENERATED_NOTICE)).not.toBeInTheDocument();
  });

  test("shows generated explanation with the honest notice", () => {
    render(<PolicyCoverageList coverages={[withExplanation]} />);

    expect(
      screen.getByText("교통사고 형사합의금을 지원해요."),
    ).toBeInTheDocument();
    expect(screen.getByText(GENERATED_NOTICE)).toBeInTheDocument();
  });

  test("renders unverified amounts as a soft ask instead of 확인필요", () => {
    render(<PolicyCoverageList coverages={[unverifiedAmount]} />);

    expect(screen.getByText("가입금액은 확인이 필요해요")).toBeInTheDocument();
    expect(screen.queryByText("확인필요")).not.toBeInTheDocument();
  });

  test("shows the empty state when there are no coverages", () => {
    render(<PolicyCoverageList coverages={[]} />);

    expect(
      screen.getByText("이 증권에서 보장 내용을 찾지 못했어요."),
    ).toBeInTheDocument();
  });

  test("shows the empty state when coverages are missing entirely", () => {
    render(<PolicyCoverageList />);

    expect(
      screen.getByText("이 증권에서 보장 내용을 찾지 못했어요."),
    ).toBeInTheDocument();
  });

  test("distinguishes a partial-analysis failure from a genuinely empty result", () => {
    render(<PolicyCoverageList coverages={[]} status="부분" />);

    expect(
      screen.getByText(
        "보장 내용을 다 불러오지 못했어요. 잠시 후 다시 시도해 주세요.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("이 증권에서 보장 내용을 찾지 못했어요."),
    ).not.toBeInTheDocument();
  });

  test("notes a partial analysis when some coverages did load", () => {
    render(<PolicyCoverageList coverages={[withDetail]} status="부분" />);

    expect(screen.getByText("암진단비")).toBeInTheDocument();
    expect(
      screen.getByText("일부 정보를 분석하지 못했어요."),
    ).toBeInTheDocument();
  });

  test("shows no partial note when analysis completed", () => {
    render(<PolicyCoverageList coverages={[withDetail]} status="완료" />);

    expect(
      screen.queryByText("일부 정보를 분석하지 못했어요."),
    ).not.toBeInTheDocument();
  });
});
