import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import DocumentList from "./pages/DocumentList";
import Review from "./pages/Review";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<DocumentList />} />
        <Route path="/documents/:id" element={<Review />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
