document.addEventListener('DOMContentLoaded', () => {
    const imageInput = document.querySelector('input[type="file"]')
    const displayImage = document.querySelector('#image-preview')
    const svg = document.querySelector('#svg')

    imageInput.addEventListener('change', (event) => {
        const imgObject = event.target.files[0]

        if (imgObject){
            displayImage.src = URL.createObjectURL(imgObject)
            displayImage.classList.remove('hidden')
            svg.classList.add('hidden')
        } else {
            displayImage.classList.add('hidden')
            svg.classList.remove('hidden')
        }

    })
});
