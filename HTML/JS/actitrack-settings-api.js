/**
 * ActiTrack Settings API 客戶端
 * 【功能】設定頁專用 API，負責教學文字的動態載入，以及未來參數編輯功能的擴充基底
 */
class ActiTrackSettingsAPI {
    constructor() {
        this.textBasePath = 'text/'; // 教學文字檔所在目錄
    }

    // 依 URL 的 ?topic= 參數讀取對應 .txt 檔，並寫入指定容器
    // 例：?topic=delete_bmi → 讀取 text/delete_bmi.txt
    async loadTutorialText(containerId) {
        const container = document.getElementById(containerId);
        if (!container) return;

        // URLSearchParams：解析 URL 的 query string，無 topic 時預設 system_guide
        const urlParams   = new URLSearchParams(window.location.search);
        const topic       = urlParams.get('topic') || 'system_guide';
        const helpTextUrl = `${this.textBasePath}${topic}.txt`;

        try {
            const response = await fetch(helpTextUrl);
            if (!response.ok) throw new Error('找不到檔案');
            const htmlContent = await response.text();
            container.innerHTML = htmlContent; // .txt 內可含 HTML 標籤
        } catch (error) {
            console.error('讀取教學檔發生錯誤:', error);
            container.innerHTML = `<span style="color:#e74c3c; font-weight:bold; font-size:1.2rem;">無法載入教學文字。<br>請確認 📁 ${helpTextUrl} 檔案是否存在。</span>`;
        }
    }

    // 預留給 Params Editor 頁面使用（尚未實作）
    async loadSystemParams() {
        console.log("準備串接後端讀取 detector_config.json...");
        // TODO: 呼叫 server.py 取得設定 JSON
    }

    async saveSystemParams(jsonData) {
        console.log("準備串接後端儲存 detector_config.json...");
        // TODO: 呼叫 server.py 儲存設定 JSON
    }
}

// 掛載至 window，供其他腳本共用
window.ActiTrackSettingsAPI = ActiTrackSettingsAPI;
if (!window.actiTrackSettings) window.actiTrackSettings = new ActiTrackSettingsAPI();
