export function loadInsuranceChatbot() {
  return import("./chatbot");
}

export function preloadInsuranceChatbot() {
  void loadInsuranceChatbot();
}
