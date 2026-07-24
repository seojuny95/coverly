import type { InsuranceAnalysis } from "../../analysis/store";

export type AnalysisProgress = {
  completed: number;
  total: number;
};

type IdleWorkflowState = {
  phase: "idle";
  analysisProgress: AnalysisProgress;
  pendingAnalysis: null;
  selectedName: "";
};

type UploadingWorkflowState = {
  phase: "uploading";
  analysisProgress: AnalysisProgress;
  pendingAnalysis: null;
  selectedName: "";
};

type PreparingServerWorkflowState = {
  phase: "preparing-server";
  analysisProgress: AnalysisProgress;
  pendingAnalysis: null;
  selectedName: "";
};

type NameSelectionWorkflowState = {
  phase: "name-selection";
  analysisProgress: AnalysisProgress;
  pendingAnalysis: InsuranceAnalysis;
  selectedName: string;
};

type CompletingWorkflowState = {
  phase: "completing";
  analysisProgress: AnalysisProgress;
  pendingAnalysis: InsuranceAnalysis | null;
  selectedName: string;
};

export type UploadWorkflowState =
  | IdleWorkflowState
  | PreparingServerWorkflowState
  | UploadingWorkflowState
  | NameSelectionWorkflowState
  | CompletingWorkflowState;

export type UploadWorkflowAction =
  | { type: "start"; total: number }
  | { type: "server-ready" }
  | { type: "uploaded" }
  | {
      type: "require-name-selection";
      analysis: InsuranceAnalysis;
      selectedName: string;
    }
  | { type: "select-name"; selectedName: string }
  | { type: "begin-completion" }
  | { type: "return-to-name-selection" }
  | { type: "finish" }
  | { type: "reset" };

export const initialUploadWorkflowState: UploadWorkflowState = {
  phase: "idle",
  analysisProgress: { completed: 0, total: 0 },
  pendingAnalysis: null,
  selectedName: "",
};

export function uploadWorkflowReducer(
  state: UploadWorkflowState,
  action: UploadWorkflowAction,
): UploadWorkflowState {
  switch (action.type) {
    case "start":
      return {
        phase: "preparing-server",
        analysisProgress: { completed: 0, total: action.total },
        pendingAnalysis: null,
        selectedName: "",
      };
    case "server-ready":
      return state.phase === "preparing-server"
        ? { ...state, phase: "uploading" }
        : state;
    case "uploaded":
      return state.phase === "uploading"
        ? {
            ...state,
            analysisProgress: {
              ...state.analysisProgress,
              completed: state.analysisProgress.completed + 1,
            },
          }
        : state;
    case "require-name-selection":
      return state.phase === "uploading"
        ? {
            phase: "name-selection",
            analysisProgress: state.analysisProgress,
            pendingAnalysis: action.analysis,
            selectedName: action.selectedName,
          }
        : state;
    case "select-name":
      return state.phase === "name-selection"
        ? { ...state, selectedName: action.selectedName }
        : state;
    case "begin-completion":
      if (state.phase === "uploading") {
        return {
          phase: "completing",
          analysisProgress: state.analysisProgress,
          pendingAnalysis: null,
          selectedName: "",
        };
      }
      if (state.phase === "name-selection") {
        return { ...state, phase: "completing" };
      }
      return state;
    case "return-to-name-selection":
      if (state.phase === "completing" && state.pendingAnalysis) {
        return {
          phase: "name-selection",
          analysisProgress: state.analysisProgress,
          pendingAnalysis: state.pendingAnalysis,
          selectedName: state.selectedName,
        };
      }
      return state;
    case "finish":
    case "reset":
      return initialUploadWorkflowState;
  }
}

export function isUploadInFlight(state: UploadWorkflowState) {
  return (
    state.phase === "preparing-server" ||
    state.phase === "uploading" ||
    state.phase === "completing"
  );
}
