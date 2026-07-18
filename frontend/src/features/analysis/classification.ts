export type DisplayClassification =
  "생명보험" | "제3보험" | "손해보험" | "미분류";

const DISPLAY_CLASSIFICATION_BY_SOURCE: Record<string, DisplayClassification> =
  {
    생명보험: "생명보험",
    "생명·연금": "생명보험",
    제3보험: "제3보험",
    "상해·질병·실손": "제3보험",
    손해보험: "손해보험",
    자동차: "손해보험",
    자동차보험: "손해보험",
    운전자보험: "손해보험",
    운전자상해보험: "손해보험",
    여행자보험: "손해보험",
    화재보험: "손해보험",
    주택화재보험: "손해보험",
    배상책임보험: "손해보험",
    보증보험: "손해보험",
    "배상·화재·기타": "손해보험",
  };

export function displayClassification(
  classification?: string,
): DisplayClassification {
  return classification
    ? (DISPLAY_CLASSIFICATION_BY_SOURCE[classification] ?? "미분류")
    : "미분류";
}

export function isDamageClassification(classification?: string): boolean {
  return displayClassification(classification) === "손해보험";
}

export function isAutoClassification(
  classification?: string,
  productTags: string[] = [],
): boolean {
  return (
    classification === "자동차" ||
    classification === "자동차보험" ||
    productTags.includes("자동차보험")
  );
}
