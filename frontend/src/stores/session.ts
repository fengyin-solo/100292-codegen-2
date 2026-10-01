import { defineStore } from 'pinia'

export interface CurrentUser {
  工号: string
  姓名: string
  单位: string
}

export const useSessionStore = defineStore('session', {
  state: () => ({
    // 默认身份取第一建设公司 P-0001 的安全员；安全费用页可切换身份验证越权/跨单位驳回
    user: {
      工号: 'S001',
      姓名: '王建国',
      单位: '第一建设公司',
    } as CurrentUser,
    shiftLabel: '白班 08:00-20:00',
    scope: '特种设备安全管理平台',
  }),
  getters: {
    operator: (state) => state.user.姓名,
    canOperate: (state) => state.user.工号.length > 0,
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setUser(user: CurrentUser) {
      this.user = user
    },
  },
})
