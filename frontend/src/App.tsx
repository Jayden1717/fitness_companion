import { useState, useEffect } from "react";
import "./App.css";

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";
const STRAVA_CLIENT_ID = import.meta.env.VITE_STRAVA_CLIENT_ID;

function App() {
  const [userId, setUserId] = useState<string>("");
  const [isStravaConnected, setIsStravaConnected] = useState<boolean>(false);
  const [weight, setWeight] = useState<string>("");
  const [ftp, setFtp] = useState<string>("");
  const [voiceTranscript, setVoiceTranscript] = useState<string>("");
  const [coachAdvice, setCoachAdvice] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(false);

  useEffect(() => {
    const storedUserId = localStorage.getItem("userId");
    if (storedUserId) {
      setUserId(storedUserId);
    }

    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get("strava_auth_success") === "true") {
      setIsStravaConnected(true);
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, []);

  const handleUserIdChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const newUserId = event.target.value;
    setUserId(newUserId);
    localStorage.setItem("userId", newUserId);
  };

  const handleConnectStrava = () => {
    if (!userId) {
      alert("Please enter a User ID first.");
      return;
    }
    if (!STRAVA_CLIENT_ID) {
      alert("Strava Client ID is not configured. Please check your .env file.");
      return;
    }

    const stravaAuthUrl = `https://www.strava.com/oauth/authorize?client_id=${STRAVA_CLIENT_ID}&response_type=code&redirect_uri=${BACKEND_URL}/strava/callback&scope=activity:read_all&state=${userId}`;
    window.location.href = stravaAuthUrl;
  };

  const handleUpdateProfile = async () => {
    if (!userId) {
      alert("Please enter a User ID.");
      return;
    }
    if (!weight && !ftp) {
      alert("Please enter either weight or FTP to update your profile.");
      return;
    }

    let transcript = `My current stats are:`;
    if (weight) transcript += ` weight ${weight}kg`;
    if (ftp) transcript += ` FTP ${ftp}W`;

    setVoiceTranscript(transcript);
    await sendToCoach(transcript);
    alert("Profile update request sent to coach.");
  };

  const sendToCoach = async (transcript: string) => {
    if (!userId) {
      alert("Please enter a User ID.");
      return;
    }
    setIsLoading(true);
    setCoachAdvice("Thinking...");
    try {
      const response = await fetch(`${BACKEND_URL}/coach`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ user_id: userId, voice_transcript: transcript }),
      });
      const data = await response.json();
      setCoachAdvice(data.advice);
    } catch (error) {
      console.error("Error sending message to coach:", error);
      setCoachAdvice("Error connecting to coach. Please try again later.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleChatSubmit = async () => {
    if (!voiceTranscript.trim()) return;
    await sendToCoach(voiceTranscript);
    setVoiceTranscript(""); // Clear input after sending
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>AI Cycling Coach</h1>
        <div className="user-id-section card">
          <label htmlFor="userId">User ID:</label>
          <input
            id="userId"
            type="text"
            value={userId}
            onChange={handleUserIdChange}
            placeholder="Enter your unique user ID"
            disabled={isStravaConnected} // Disable if connected to Strava
          />
        </div>

        <div className="strava-section card">
          {isStravaConnected ? (
            <p>Strava Connected! You can now chat with your coach.</p>
          ) : (
            <button onClick={handleConnectStrava} disabled={!userId}>
              Connect to Strava
            </button>
          )}
        </div>

        {userId && isStravaConnected && (
          <div className="main-content">
            <div className="user-profile-inputs card">
              <h2>Your Profile</h2>
              <div>
                <label htmlFor="weight">Weight (kg):</label>
                <input
                  id="weight"
                  type="number"
                  value={weight}
                  onChange={(e) => setWeight(e.target.value)}
                  placeholder="e.g., 70"
                />
              </div>
              <div>
                <label htmlFor="ftp">FTP (Watts):</label>
                <input
                  id="ftp"
                  type="number"
                  value={ftp}
                  onChange={(e) => setFtp(e.target.value)}
                  placeholder="e.g., 250"
                />
              </div>
              <button onClick={handleUpdateProfile} disabled={isLoading}>
                Update Profile via Coach
              </button>
            </div>

            <div className="chat-interface card">
              <h2>Chat with your Coach</h2>
              <div className="coach-response">
                <p>
                  Coach: {coachAdvice || "Hello! How can I help you today?"}
                </p>
              </div>
              <textarea
                value={voiceTranscript}
                onChange={(e) => setVoiceTranscript(e.target.value)}
                placeholder="Ask your coach a question... (e.g., 'What should I do today?' or 'My new weight is 75kg')"
                rows={4}
              ></textarea>
              <button
                onClick={handleChatSubmit}
                disabled={isLoading || !userId || !voiceTranscript.trim()}
              >
                {isLoading ? "Sending..." : "Send to Coach"}
              </button>
            </div>
          </div>
        )}
      </header>
    </div>
  );
}

export default App;
