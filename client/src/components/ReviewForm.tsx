import React, { useState } from 'react';
import { Star, Send } from 'lucide-react';
import axios from 'axios';

interface ReviewFormProps {
  placeId: number;
  onSuccess: () => void;
}

const ReviewForm: React.FC<ReviewFormProps> = ({ placeId, onSuccess }) => {
  const [content, setContent] = useState('');
  const [rating, setRating] = useState(5);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await axios.post('/api/reviews', { placeId, content, rating });
      setContent('');
      onSuccess();
    } catch (err) {
      console.error('Failed to submit review', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="mt-6 p-4 bg-gray-50 rounded-2xl">
      <h3 className="font-bold mb-3">Leave a review</h3>
      <div className="flex gap-1 mb-3">
        {[1, 2, 3, 4, 5].map((star) => (
          <button
            key={star}
            type="button"
            onClick={() => setRating(star)}
            className={`${rating >= star ? 'text-yellow-400' : 'text-gray-300'}`}
          >
            <Star size={24} fill={rating >= star ? 'currentColor' : 'none'} />
          </button>
        ))}
      </div>
      <textarea
        className="w-full p-3 border rounded-xl outline-none focus:ring-2 focus:ring-blue-500 bg-white"
        placeholder="Share your experience..."
        rows={3}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        required
      />
      <button
        type="submit"
        disabled={isSubmitting}
        className="mt-3 w-full bg-blue-600 text-white py-2 rounded-xl font-bold flex items-center justify-center gap-2 disabled:bg-blue-300"
      >
        <Send size={18} />
        {isSubmitting ? 'Posting...' : 'Post Review'}
      </button>
    </form>
  );
};

export default ReviewForm;
