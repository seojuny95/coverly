import type { InsuranceAnalysis } from "../../analysis/types";

export type UploadProgress = {
  completed: number;
  total: number;
};

type IdlePolicyUploadState = {
  phase: "idle";
  analysisProgress: UploadProgress;
  pendingAnalysis: null;
  selectedName: "";
};

type UploadingPolicyUploadState = {
  phase: "uploading";
  analysisProgress: UploadProgress;
  pendingAnalysis: null;
  selectedName: "";
};

type PreparingServerPolicyUploadState = {
  phase: "preparing-server";
  analysisProgress: UploadProgress;
  pendingAnalysis: null;
  selectedName: "";
};

type NameSelectionPolicyUploadState = {
  phase: "name-selection";
  analysisProgress: UploadProgress;
  pendingAnalysis: InsuranceAnalysis;
  selectedName: string;
};

type CompletingPolicyUploadState = {
  phase: "completing";
  analysisProgress: UploadProgress;
  pendingAnalysis: InsuranceAnalysis | null;
  selectedName: string;
};

export type UploadInFlightState =
  | PreparingServerPolicyUploadState
  | UploadingPolicyUploadState
  | CompletingPolicyUploadState;

export type PolicyUploadState =
  IdlePolicyUploadState | UploadInFlightState | NameSelectionPolicyUploadState;

export type PolicyUploadAction =
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

export const initialPolicyUploadState: PolicyUploadState = {
  phase: "idle",
  analysisProgress: { completed: 0, total: 0 },
  pendingAnalysis: null,
  selectedName: "",
};

export function policyUploadReducer(
  state: PolicyUploadState,
  action: PolicyUploadAction,
): PolicyUploadState {
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
      return initialPolicyUploadState;
  }
}

export function isUploadInFlight(
  state: PolicyUploadState,
): state is UploadInFlightState {
  return (
    state.phase === "preparing-server" ||
    state.phase === "uploading" ||
    state.phase === "completing"
  );
}
