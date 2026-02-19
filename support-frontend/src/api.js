import axios from "axios"

const isBrowser = typeof window !== "undefined"
const envBase = (import.meta.env.VITE_API_BASE_URL || "").trim()
const defaultDevHost = "127.0.0.1"
const defaultDevPort = 8002

const inferBaseFromWindow = () => {
	if (!isBrowser) {
		return `http://${defaultDevHost}:${defaultDevPort}`
	}
	const { protocol, hostname, port } = window.location
	const currentOrigin = `${protocol}//${hostname}${port ? `:${port}` : ""}`
	const isViteDevPort = port === "5173"
	if (isViteDevPort) {
		return `${protocol}//${hostname}:${defaultDevPort}`
	}
	return currentOrigin
}

const API = envBase || inferBaseFromWindow()

export const UNAUTHORIZED_EVENT = "support-unauthorized"

const client = axios.create({
	baseURL: API,
	withCredentials: true,
	headers: { "Content-Type": "application/json" },
})

client.interceptors.response.use(
	(response) => response,
	(error) => {
		if (error.response?.status === 401 && typeof window !== "undefined") {
			window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
		}
		return Promise.reject(error)
	},
)

export const getTickets = () => client.get("/tickets")
export const syncEmails = () => client.post("/sync-emails")
export const sendReply = (id) =>
	client.post(`/send-reply/${id}`, { confirm: true })
export const updateReply = (id, text) =>
	client.put(`/update-reply/${id}`, { reply: text })
export const login = (username, password) =>
	client.post("/login", { username, password })
export const logout = () => client.post("/logout")
export const checkSession = () => client.get("/session")
