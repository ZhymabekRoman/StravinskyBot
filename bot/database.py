import sqlite3


class SQLighter:
    def __init__(self, database):
        self.connection = sqlite3.connect(database)
        self.connection.execute("PRAGMA foreign_keys = ON")  # Need for working with foreign keys in db
        self.cursor = self.connection.cursor()

    def init(self):
        with self.connection:
            self.cursor.execute("CREATE TABLE if not exists users(user_id INTEGER NOT NULL PRIMARY KEY, user_name TEXT NOT NULL)")
            self.cursor.execute("CREATE TABLE if not exists folders(folder_id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, folder_name TEXT NOT NULL, user_id INTEGER NOT NULL, FOREIGN KEY (user_id) REFERENCES users(user_id))")
            self.cursor.execute("CREATE TABLE if not exists audio_samples(audio_sample_id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, audio_sample_name TEXT NOT NULL, folder_id INTEGER NOT NULL, file_unique_id TEXT NOT NULL,FOREIGN KEY(folder_id) REFERENCES folders(folder_id))")

    def select_user(self, user_id):
        with self.connection:
            return self.cursor.execute("SELECT * FROM users WHERE user_id= :0", {'0': user_id}).fetchone()

    def create_user(self, user_id, user_name) -> None:
        with self.connection:
            self.cursor.execute("INSERT INTO users VALUES (:0, :1)", {'0': user_id, '1': user_name})

    def select_user_folders(self, user_id):
        with self.connection:
            result = self.cursor.execute("SELECT * FROM folders Where user_id= :0", {'0': user_id}).fetchall()
            return result

    def select_folder_samples(self, folder_id):
        with self.connection:
            result = self.cursor.execute("SELECT * FROM audio_samples WHERE folder_id= :0", {'0': folder_id}).fetchall()
            return result

    def select_folder(self, folder_id):
        with self.connection:
            return self.cursor.execute("SELECT * FROM folders WHERE folder_id= :0", {'0': folder_id}).fetchone()

    def create_folder(self, user_id, folder_name) -> None:
        with self.connection:
            self.cursor.execute("INSERT INTO folders (folder_name, user_id) VALUES (:0, :1)", {'0': folder_name, '1': user_id})

    def delete_folder(self, folder_id) -> None:
        with self.connection:
            self.cursor.execute("DELETE FROM folders WHERE folder_id= :0", {'0': folder_id})

    def select_audio_sample(self, sample_id):
        # TODO
        pass

    def register_audio_sample(self, folder_id, audio_sample_name, file_id) -> None:
        with self.connection:
            self.cursor.execute("INSERT INTO audio_samples (audio_sample_name, folder_id, file_unique_id) VALUES (:0, :1, :2)", {'0': audio_sample_name, '1': folder_id, '2': file_id})

    def unregister_audio_sample(self, folder_id, sample_name) -> None:
        with self.connection:
            self.cursor.execute("DELETE FROM audio_samples WHERE audio_sample_name= :0 AND folder_id= :1", {'0': sample_name, '1': folder_id})
