import { Button } from "@/shared/components/ui/button";
import { Card } from "@/shared/components/ui/card";
import { Label } from "@/shared/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/shared/components/ui/radio-group";
import {
  type AnalyzedInsurance,
  getInsuredPersonName,
} from "../../analysis/types";

export function InsuredPersonSelection({
  documents,
  selectedName,
  onSelectedNameChange,
  onContinue,
}: {
  documents: AnalyzedInsurance[];
  selectedName: string;
  onSelectedNameChange: (name: string) => void;
  onContinue: () => void;
}) {
  const options = getInsuredPersonOptions(documents);

  return (
    <Card shadow="zinc" className="mt-4 rounded-xl px-4 py-4">
      <p className="text-sm font-semibold text-zinc-950">
        피보험자가 여러 명 있어요
      </p>
      <p className="mt-1 text-sm leading-6 text-zinc-500">
        결과로 볼 피보험자를 선택하세요. 선택한 피보험자의 증권만 보여드려요.
      </p>

      <RadioGroup
        value={selectedName}
        onValueChange={onSelectedNameChange}
        name="insurance-person-name"
        className="mt-4 gap-2"
      >
        {options.map((option, index) => {
          const inputId = `insurance-person-name-${index}`;
          return (
            <Label
              key={option.name}
              htmlFor={inputId}
              className={`flex cursor-pointer items-center justify-between rounded-lg border px-3 py-3 text-sm font-normal transition-colors ${
                selectedName === option.name
                  ? "border-blue-600 bg-blue-50"
                  : "border-zinc-200 bg-white hover:bg-zinc-50"
              }`}
            >
              <span className="flex items-center gap-3">
                <RadioGroupItem id={inputId} value={option.name} />
                <span className="font-medium text-zinc-800">{option.name}</span>
              </span>
              <span className="text-zinc-500">{option.count}개</span>
            </Label>
          );
        })}
      </RadioGroup>

      <Button
        type="button"
        onClick={onContinue}
        disabled={!selectedName}
        className="mt-4"
      >
        선택한 피보험자로 보기
      </Button>
    </Card>
  );
}

function getInsuredPersonOptions(documents: AnalyzedInsurance[]) {
  const counts = new Map<string, number>();
  for (const document of documents) {
    const name = getInsuredPersonName(document);
    if (!name) continue;
    counts.set(name, (counts.get(name) ?? 0) + 1);
  }

  return Array.from(counts, ([name, count]) => ({ name, count }));
}
