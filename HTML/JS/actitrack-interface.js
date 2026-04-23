// DOM載入完成後再執行，確保元素都已存在
document.addEventListener('DOMContentLoaded', () => {

    // 外部介紹文字檔的路徑
    const helpTextUrl = 'text/ActiTrack_Interface_help.txt';

    // 取得顯示目標元素（對應HTML的 id="dynamic-help-text"）
    const container = document.getElementById('dynamic-help-text');

    // 確認元素存在再執行，避免錯誤
    if (container) {

        // 用 fetch 非同步讀取外部檔案
        fetch(helpTextUrl)

            // ① 確認回應是否成功，失敗則拋出錯誤交給 catch 處理
            .then(response => {
                if (!response.ok) {
                    throw new Error('找不到介紹檔案或讀取失敗');
                }
                return response.text(); // 將回應轉為字串
            })

            // ② 將取得的內容（含HTML標籤）直接渲染到畫面
            .then(htmlContent => {
                container.innerHTML = htmlContent;
            })

            // 任何錯誤都在此處理：主控台記錄 + 畫面顯示紅字提示
            .catch(error => {
                console.error('讀取說明檔發生錯誤:', error);
                container.innerHTML = '<span style="color: red;">無法載入系統介紹文字，請確認 text/ActiTrack_Interface_help.txt 檔案是否存在。</span>';
            });
    }
});