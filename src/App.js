import React, { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios'; // 백엔드 서버와 통신하기 위한 라이브러리
import './ProductPageGenerator.css';

function ProductPageGenerator() {
  // 상태 변수 설정
  const [imageFiles, setImageFiles] = useState([]); // 업로드한 이미지 파일
  const [imageData, setImageData] = useState([]); // 이미지별 데이터 (URL, 번역된 텍스트, 수정된 텍스트)

  const [isLoading, setIsLoading] = useState(false); // 로딩 상태
  const [isDragging, setIsDragging] = useState(false); // 드래그 상태
  const dropRef = useRef(null);


  const handleFiles = useCallback((files) => {
    setImageFiles(files);
    
    // 이미지 미리보기 URL 생성
    const newImageData = files.map(file => ({
      url: URL.createObjectURL(file),
      originalText: '',
      translatedText: '번역 대기 중...',
      editedText: ''
    }));
    setImageData(newImageData);
  }, []);

  const handleImageChange = (e) => {
    const files = Array.from(e.target.files);
    handleFiles(files);
  };

  useEffect(() => {
    const handlePaste = (event) => {
      const items = (event.clipboardData || event.originalEvent.clipboardData).items;
      const files = [];
      for (let i = 0; i < items.length; i++) {
        if (items[i].type.indexOf('image') !== -1) {
          files.push(items[i].getAsFile());
        }
      }
      if (files.length > 0) {
        handleFiles(files);
      }
    };

    const dropElement = dropRef.current;
    if (dropElement) {
      dropElement.addEventListener('paste', handlePaste);
    }

    return () => {
      if (dropElement) {
        dropElement.removeEventListener('paste', handlePaste);
      }
    };
  }, [handleFiles]);

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files);
    if (files && files.length > 0) {
      handleFiles(files);
    }
  };

  // '번역 및 텍스트 생성' 버튼 클릭 시 실행
  const handleProcessImages = async () => {
    if (imageFiles.length === 0) {
      alert("이미지를 먼저 업로드해주세요.");
      return;
    }
    setIsLoading(true);

    // 각 이미지에 대해 OCR 및 번역 요청
    const processingPromises = imageFiles.map(async (file, index) => {
      const formData = new FormData();
      formData.append('image', file);
      
      try {
        // 백엔드(Python) 서버로 이미지 전송 및 결과 수신
        const response = await axios.post('/api/process-image', formData, {
          headers: {
            'Content-Type': 'multipart/form-data'
          }
        });

        // 수신된 데이터로 상태 업데이트
        const { result } = response.data;
        return {
          ...imageData[index],
          translatedText: result,
          editedText: `// 참고: 여기서 추가 수정하세요.\n${result}`
        };
      } catch (error) {
        console.error("Error processing image:", error);
        return {
          ...imageData[index],
          translatedText: "번역 실패",
          editedText: "오류가 발생했습니다."
        };
      }
    });

    const newData = await Promise.all(processingPromises);
    setImageData(newData);
    setIsLoading(false);
  };


  
  // 수정된 텍스트 변경 시 상태 업데이트
  const handleTextChange = (index, value) => {
    const updatedImageData = [...imageData];
    updatedImageData[index].editedText = value;
    setImageData(updatedImageData);
  };

  // HTML 파일 생성 및 다운로드
  const handleDownloadHtml = () => {
    let htmlContent = `
      <!DOCTYPE html>
      <html lang="ko">
      <head>
        <meta charset="UTF-8">
        <title>이미지 텍스트 번역</title>
        <style>
          body { font-family: 'Pretendard', sans-serif; margin: 0; padding: 0; }
          .item-section { text-align: center; margin-bottom: 50px; }
          img { max-width: 100%; height: auto; }
          p { white-space: pre-wrap; font-size: 16px; line-height: 1.6; color: #333; }
        </style>
      </head>
      <body>
    `;

    imageData.forEach(item => {
      htmlContent += `
        <div class="item-section">
          <img src="${item.url}" alt="상품 이미지">
          <p>${item.editedText}</p>
        </div>
      `;
    });

    htmlContent += '</body></html>';
    
    const blob = new Blob([htmlContent], { type: 'text/html;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'product_detail.html');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleDownloadText = () => {
    const textContent = imageData.map(item => item.editedText).join('\n\n---\n\n');
    const blob = new Blob([textContent], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'translated_text.txt');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  return (
    <div className="product-page-generator" ref={dropRef} tabIndex="0">
      <h1>이미지 텍스트 번역기</h1>
      
      {/* 1. 이미지 업로드 */}
      <div 
        className={`upload-section ${isDragging ? 'dragging' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <input type="file" accept="image/*" multiple onChange={handleImageChange} />
        <p>여기에 파일을 드래그하거나 클릭하여 업로드하세요.</p>
      </div>

      

        <button onClick={handleProcessImages} disabled={isLoading} className="process-button">
          {isLoading ? '처리 중...' : '번역 및 텍스트 생성'}
        </button>



      {/* 2. 결과 */}
      <div className="image-data-container">
        {imageData.map((item, index) => (
          <div key={index} className="image-data-item">
            <img src={item.url} alt={`preview-${index}`} className="preview-image" />
            <div className="text-editor-section">
              <h4>번역된 텍스트 (수정 가능)</h4>
              <p><strong>참고 스타일:</strong> 보내주신 예시처럼 감성적이고 부드러운 문구로 다듬어보세요. (예: "일상에 특별함을 더해 줄 작은 포인트")</p>
              <textarea
                value={item.editedText}
                onChange={(e) => handleTextChange(index, e.target.value)}
                className="text-editor"
              />
            </div>
          </div>
        ))}

      </div>
      
      {/* 3. 다운로드 */}
      {imageData.length > 0 && !isLoading && (
        <>
          <button onClick={handleDownloadText} className="download-button">
            텍스트 다운로드
          </button>
          <button onClick={handleDownloadHtml} className="download-button">
            최종 상세페이지 HTML 다운로드
          </button>
        </>
      )}
    </div>
  );
}

export default ProductPageGenerator;

