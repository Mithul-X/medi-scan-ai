"use client";

import { useCallback, useRef, useState } from "react";

const ACCEPTED_TYPES = [
  "application/pdf",
  "image/png",
  "image/jpeg",
  "image/webp",
  "text/plain",
];
const ACCEPTED_EXTENSIONS = ".pdf,.png,.jpg,.jpeg,.webp,.txt";

interface FileUploadProps {
  onUpload: (file: File) => void;
  isLoading: boolean;
}

export default function FileUpload({ onUpload, isLoading }: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const validateAndUpload = useCallback(
    (file: File) => {
      setError(null);
      if (!ACCEPTED_TYPES.includes(file.type)) {
        setError(
          `Unsupported file type. Use PDF, PNG, JPEG, WebP, or plain text.`
        );
        return;
      }
      if (file.size > 10 * 1024 * 1024) {
        setError("File exceeds 10MB limit.");
        return;
      }
      onUpload(file);
    },
    [onUpload]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file) validateAndUpload(file);
    },
    [validateAndUpload]
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) validateAndUpload(file);
      e.target.value = "";
    },
    [validateAndUpload]
  );

  return (
    <div className="upload-wrapper">
      <div
        className={`upload-zone ${isDragging ? "upload-zone-active" : ""} ${
          isLoading ? "upload-zone-disabled" : ""
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          if (!isLoading) setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={isLoading ? undefined : handleDrop}
        onClick={() => !isLoading && inputRef.current?.click()}
        role="button"
        tabIndex={0}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_EXTENSIONS}
          onChange={handleFileInput}
          className="upload-input-hidden"
          disabled={isLoading}
        />
        {isLoading ? (
          <div className="upload-status">
            <span className="upload-spinner" aria-hidden="true" />
            <p className="upload-status-text">Analyzing report&hellip;</p>
          </div>
        ) : (
          <div className="upload-status">
            <p className="upload-primary-text">
              Drop a medical report here, or click to browse
            </p>
            <p className="upload-secondary-text">
              PDF, PNG, JPEG, WebP, or plain text &middot; up to 10MB
            </p>
          </div>
        )}
      </div>
      {error && <p className="upload-error">{error}</p>}
    </div>
  );
}
