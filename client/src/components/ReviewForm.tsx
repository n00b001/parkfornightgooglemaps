import React, { useState } from "react";
import { Star, Send } from "lucide-react";
import { api } from "../lib/api";
import { savePendingReview } from "../services/db";

const ReviewForm: React.FC<any> = ({ placeId, onSuccess }) => {
	const [content, setContent] = useState("");
	const [rating, setRating] = useState(5);

	const handleSubmit = async (e: React.FormEvent) => {
		e.preventDefault();
		const reviewData = { placeId, content, rating };
		try {
			await api("add-review", {
				method: "POST",
				body: reviewData,
			});
			setContent("");
			onSuccess();
		} catch (err) {
			if (!navigator.onLine) {
				await savePendingReview(reviewData);
				setContent("");
				alert(
					"You are offline. Your review has been saved and will be uploaded when you are back online.",
				);
				onSuccess();
			} else {
				console.error(err);
			}
		}
	};

	return (
		<form onSubmit={handleSubmit} className="mt-4 p-4 bg-gray-50 rounded-xl">
			<div className="flex gap-1 mb-2">
				{[1, 2, 3, 4, 5].map((s) => (
					<button key={s} type="button" onClick={() => setRating(s)}>
						<Star size={16} fill={rating >= s ? "orange" : "none"} />
					</button>
				))}
			</div>
			<textarea
				className="w-full p-2 border rounded-lg text-sm"
				value={content}
				onChange={(e) => setContent(e.target.value)}
				placeholder="Write a review..."
			/>
			<button
				type="submit"
				className="mt-2 w-full bg-blue-600 text-white py-2 rounded-lg text-sm font-bold flex items-center justify-center gap-1"
			>
				<Send size={14} /> Post
			</button>
		</form>
	);
};

export default ReviewForm;
