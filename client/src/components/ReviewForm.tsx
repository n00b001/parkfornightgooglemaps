import { useState } from 'react';
import axios from 'axios';
import { Star, Send } from 'lucide-react';

interface ReviewFormProps {
  placeId: number;
  onSuccess: () => void;
}

const ReviewForm: React.FC<ReviewFormProps> = ({ placeId, onSuccess }) => {
  const [content, setContent] = useState('');
  const [rating, setRating] = useState(5);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim()) return;

    setSubmitting(true);
    try {
      await axios.post('/api/reviews', { placeId, content, rating });
      setContent('');
      setRating(5);
      onSuccess();
    } catch (err) {
      console.error(err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="bg-blue-50/50 p-4 rounded-2xl border border-blue-100">
      <div className="flex items-center gap-2 mb-3">
        {[1, 2, 3, 4, 5].map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setRating(s)}
            className="transition-transform active:scale-90"
          >
            <Star
              size={20}
              className={s <= rating ? 'text-yellow-500' : 'text-gray-300'}
              fill={s <= rating ? 'currentColor' : 'none'}
            />
          </button>
        ))}
        <span className="text-xs font-bold text-blue-600 ml-auto">{rating}/5 stars</span>
      </div>
      <div className="relative">
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Share your experience..."
          className="w-full bg-white border-none rounded-xl p-3 text-sm text-gray-700 placeholder-gray-400 focus:ring-2 focus:ring-blue-500 outline-none resize-none h-20 shadow-sm"
        />
        <button
          type="submit"
          disabled={submitting || !content.trim()}
          className="absolute bottom-2 right-2 p-2 bg-blue-600 text-white rounded-lg shadow-md hover:bg-blue-700 disabled:bg-gray-300 disabled:shadow-none transition-all"
        >
          <Send size={16} />
        </button>
      </div>
    </form>
  );
};

export default ReviewForm;
