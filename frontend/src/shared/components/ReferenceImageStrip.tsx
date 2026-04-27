import { useEffect, useMemo, useState } from "react";

import type { ReferenceImageDisplay } from "../../types/domain";

interface ReferenceImageStripProps {
  images?: ReferenceImageDisplay[];
  imageUrls?: string[];
  title?: string;
  source?: string;
  idPrefix?: string;
  variant?: "message" | "card";
}

export function ReferenceImageStrip({
  images,
  imageUrls,
  title = "参考图片",
  source = "",
  idPrefix = "reference-image",
  variant = "card",
}: ReferenceImageStripProps) {
  const [selectedImage, setSelectedImage] = useState<ReferenceImageDisplay | null>(null);
  const [zoom, setZoom] = useState(1);
  const normalizedImages = useMemo(
    () =>
      images ||
      (imageUrls || [])
        .filter((url) => url.trim().length > 0)
        .map((url, index) => ({
          id: `${idPrefix}-${index}-${url}`,
          url,
          title,
          source,
        })),
    [idPrefix, imageUrls, images, source, title],
  );

  useEffect(() => {
    if (!selectedImage) return;

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setSelectedImage(null);
        setZoom(1);
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [selectedImage]);

  if (!normalizedImages.length) return null;

  return (
    <>
      <div className={`reference-image-strip ${variant}`} aria-label="相关参考图片">
        {normalizedImages.map((image) => (
          <button
            key={image.id}
            type="button"
            className="reference-image-button"
            aria-label={`放大查看${image.title}参考图`}
            onClick={() => {
              setSelectedImage(image);
              setZoom(1);
            }}
          >
            <img
              src={image.url}
              alt={`${image.title}参考图`}
              title={[image.title, image.source].filter(Boolean).join(" · ")}
              loading="lazy"
              onError={(event) => {
                event.currentTarget.hidden = true;
                event.currentTarget.closest("button")?.setAttribute("hidden", "true");
              }}
            />
          </button>
        ))}
      </div>
      {selectedImage ? (
        <div
          className="image-lightbox"
          role="dialog"
          aria-modal="true"
          aria-label="参考图片预览"
          onClick={() => {
            setSelectedImage(null);
            setZoom(1);
          }}
        >
          <div className="image-lightbox-panel" onClick={(event) => event.stopPropagation()}>
            <header>
              <div>
                <strong>{selectedImage.title}</strong>
                {selectedImage.source ? <span>{selectedImage.source}</span> : null}
              </div>
              <button
                type="button"
                className="ghost-button"
                onClick={() => {
                  setSelectedImage(null);
                  setZoom(1);
                }}
              >
                关闭
              </button>
            </header>
            <div className="image-lightbox-stage">
              <img
                src={selectedImage.url}
                alt={`${selectedImage.title}参考图`}
                style={{
                  width: `${zoom * 100}%`,
                  maxWidth: `${zoom * 860}px`,
                  maxHeight: zoom <= 1 ? "64vh" : "none",
                }}
              />
            </div>
            <div className="image-lightbox-controls">
              <button
                type="button"
                onClick={() => setZoom((value) => Math.max(0.75, Number((value - 0.25).toFixed(2))))}
              >
                缩小
              </button>
              <span>{Math.round(zoom * 100)}%</span>
              <button
                type="button"
                onClick={() => setZoom((value) => Math.min(3, Number((value + 0.25).toFixed(2))))}
              >
                放大
              </button>
              <button type="button" onClick={() => setZoom(1)}>
                还原
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
