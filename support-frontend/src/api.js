import axios from "axios"

const HOST =
	typeof window !== "undefined" && window.location?.hostname
		? window.location.hostname
		: "127.0.0.1"
const API =
	typeof window !== "undefined" && window.location.hostname === "localhost"
		? `http://${HOST}:8000`
		: "https://supportautomation.onrender.com"
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
