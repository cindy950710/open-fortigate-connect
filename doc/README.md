# FortiGate VPN Login 文件導覽 (Documentation)

歡迎查閱 `fortigate-vpn-login` 相關技術與問題排除手冊。

## 目錄導覽

- [Windows 11 SAML SSL-VPN 疑難排解與架構���術手冊 (troubleshooting.md)](troubleshooting.md)
  - 核心架構與 SAML SSO 認證生命週期時序圖
  - 錯誤一：`AttributeError: 'Namespace' object has no attribute 'foreground'` 與 `os.uname` 相容性修復
  - 錯誤二：OpenConnect 執行檔路徑搜尋與版本檢測邏輯重構
  - 錯誤三：URL 協定缺失 `InvalidSchema` 修復與自動規格化
  - 現象四：瀏覽器未出現帳密輸入欄位之微軟 Entra ID SSO 認證機制剖析
  - 現象五：本機回呼 `http://127.0.0.1:8020/?id=...` 與 Token 兌換過程
  - 現象六：Windows 黑色終端機閃退原因與批次檔 Runner (`pause`) 防閃退防護
  - 程式碼修改紀錄與手動維護指令清單

---

## 快速使用指引 (Windows)

### 1. 必要環境
1. **Python 3.8+** (建議 3.10 ~ 3.13)
2. **OpenConnect** (建議安裝 [OpenConnect-GUI](https://github.com/openconnect/openconnect-gui) 或最新 Windows 版 OpenConnect)

### 2. 安裝與設定
在專案根目錄下以可編輯模式安裝：
```powershell
pip install -e .
```

初次執行時會提示輸入 VPN 伺服器網址，例如：
```text
https://tcgroupvpn.turn2cloud.com:18443
```

### 3. 發起連線
```powershell
fortigate-vpn-login
```
瀏覽器將會自動跳出完成微軟 SSO 身分驗證，驗證完成後即會透過 OpenConnect ���立 SSL-VPN 連線。
### 4. 結束 / 中斷 VPN 連線
有多種方式可以結束 VPN：

1. **指令快速中斷（最推薦）**：
   在任意終端���輸入：
   ```powershell
   fortigate-vpn-login -k
   # 或
   fortigate-vpn-login --disconnect
   ```
2. **在控制台視窗按下中斷鍵（標準優雅退出）**：
   在標題為 `FortiGate OpenConnect VPN` 的黑色視窗中，按下 <kbd>Ctrl</kbd> + <kbd>C</kbd>。OpenConnect 將向 FortiGate 伺服器發送正常登出通知，並自動還原路由與 DNS 設定。
3. **PowerShell 手動終止**：
   ```powershell
   Stop-Process -Name openconnect -Force
   ```