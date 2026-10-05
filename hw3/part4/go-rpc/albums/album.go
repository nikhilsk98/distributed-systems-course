package albums

/*
* Definer and storage of albums for the KV_PROTOCOL.
 */

import (
	"errors"
	"fmt"
	"strings"
)

// ///////////////////////// ALBUM METHODS /////////////////////////
// Album represents data about a record album.
type Album struct {
	id     string
	title  string
	artist string
	price  float64
}

/*
 * Returns true if and only if the albums have the same title, artist, and price.
 *
 * INPUT: that: the other album to check against
 * OUTPUT: if the albums are equal as defined in the purpose statement
 */
func (this Album) is_equal(that Album) bool {
	return (this.title == that.title) &&
		(this.artist == that.artist) &&
		(this.price == that.price)
}

/*
 * Returns the title of the album.
 *
 * OUTPUT: title of the album
 */
func (this Album) Title() string {
	return this.title
}

/*
 * Returns the artist of the album.
 *
 * OUTPUT: artist of the album
 */
func (this Album) Artist() string {
	return this.artist
}

/*
 * Returns the price of the album.
 *
 * OUTPUT: price of the album
 */
func (this Album) Price() float64 {
	return this.price
}

// albums slice to seed record album data.
var albums = []Album{
	{id: "0", title: "Blue Train", artist: "John Coltrane", price: 56.99},
	{id: "1", title: "Jeru", artist: "Gerry Mulligan", price: 17.99},
	{id: "2", title: "Sarah Vaughan and Clifford Brown", artist: "Sarah Vaughan", price: 39.99},
}

// ///////////////////////// ALBUM STORAGE METHODS /////////////////////////

/*
 * Takes the title, artist, and price and stores them if not already
 * in the storage. Returns the id associated with the album.
 *
 * INPUT: title : title of the album to store
 *        artist: artist of the album to store
 *        price : price of the album
 * OUTPUT: the id of the album
 * SIDE-EFFECTS: If the album is not already in storage, it is added to storage
 */
func Store_album(title, artist string, price float64) uint {
	album_to_store := Album{"-1", title, artist, price}
	present, id_num := containsAlbum(album_to_store)
	if present {
		return id_num
	}
	album_to_store.id = fmt.Sprintf("%v", id_num)
	albums = append(albums, album_to_store)
	return id_num
}

// Checks if the album is in storage.
// If so, returns both that and the index
// of the album.
// If not, returns that and the new index for the album in storage.
func containsAlbum(that Album) (bool, uint) {
	for idx, album := range albums {
		if album.is_equal(that) {
			return true, uint(idx)
		}
	}
	return false, uint(len(albums))
}

/*
 * Returns a copy of the album storage.
 *
 * OUTPUT: Slice representing a copy of the album storage
 */
func Retrieve_all() []Album {
	result := make([]Album, len(albums))
	copy(result, albums)
	return result
}

/*
 * Returns a copy of the album storage with albums whose titles
 * contain the given phrase.
 *
 * INPUT: phrase: the phrase to search in the titles of albums
 * OUTPUT: Slice representing a copy of the album storage with only
 *        albums whose titles contain the given phrase
 */
func Search_titles_with_phrase(phrase string) []Album {
	result := make([]Album, 0)
	for _, album := range albums {
		if strings.Contains(album.title, phrase) {
			result = append(result, album)
		}
	}
	return result
}

/*
 * Returns a reference to the album associated with that id.
 * If no such album exists in storage, throws an error.
 *
 * INPUT: id: the id of the album in storage
 * OUTPUT: pointer to the album associated with the id and an error
 *         if no such album exists in storage
 */
func Retrieve_by_id(id string) (*Album, error) {
	for _, album := range albums {
		if album.id == id {
			return &album, nil
		}
	}
	return nil, errors.New("ID not found")
}
