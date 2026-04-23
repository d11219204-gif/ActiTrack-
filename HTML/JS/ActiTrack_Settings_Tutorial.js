// ActiTrack_Settings_Tutorial.js
// 【功能】從外部 .txt 檔動態載入教學說明文字，填入指定的 div

document.addEventListener('DOMContentLoaded', () => {
    const helpTextUrl = 'text/ActiTrack_Settings_Tutorial_help.txt'; // 教學文字檔路徑
    const container   = document.getElementById('dynamic-tutorial-text');

    if (container) {
        fetch(helpTextUrl)
            .then(response => {
                if (!response.ok) throw new Error('找不到教學檔案或讀取失敗');
                return response.text(); // 取得純文字（非 JSON）
            })
            .then(htmlContent => {
                container.innerHTML = htmlContent; // 將文字內容直接寫入 DOM（支援 HTML 標籤）
            })
            .catch(error => {
                console.error('讀取教學檔發生錯誤:', error);
                container.innerHTML = '<span style="color:red; font-weight:bold;">無法載入系統教學文字，請確認 text/ActiTrack_Settings_Tutorial_help.txt 檔案是否存在。</span>';
            });
    }
});
